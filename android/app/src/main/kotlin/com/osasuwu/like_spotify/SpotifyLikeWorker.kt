package com.osasuwu.like_spotify

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL

/**
 * Minimal background worker for liking the current Spotify track.
 *
 * Business logic (playlist management, like counting, artist follow) now lives
 * in the shared Dart layer ([SpotifyMusicServiceRepository.likeTrack]).
 * This worker only handles the core like operation for when the Flutter engine
 * is not active (background media-button trigger via WorkManager).
 */
class SpotifyLikeWorker(
    appContext: Context,
    params: WorkerParameters
) : Worker(appContext, params) {

    override fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)
        var accessToken = prefs.getString(AppConstants.KEY_SPOTIFY_ACCESS_TOKEN, null)
        val refreshToken = prefs.getString(AppConstants.KEY_SPOTIFY_REFRESH_TOKEN, null)
        val clientId = prefs.getString(AppConstants.KEY_SPOTIFY_CLIENT_ID, null)

        if (accessToken.isNullOrBlank()) {
            log("Like skipped: Spotify access token missing")
            playFeedbackTone(success = false)
            return Result.success()
        }

        // Proactive token refresh: if token expires within 5 minutes
        val expiresAt = prefs.getLong(AppConstants.KEY_SPOTIFY_EXPIRES_AT, 0L)
        val nowSec = System.currentTimeMillis() / 1000L
        if (expiresAt > 0 && (expiresAt - nowSec) < 300 && !refreshToken.isNullOrBlank() && !clientId.isNullOrBlank()) {
            log("Token expires in ${expiresAt - nowSec}s, refreshing...")
            val refreshed = refreshAccessToken(refreshToken, clientId)
            if (refreshed != null && refreshed.accessToken.isNotBlank()) {
                accessToken = refreshed.accessToken
                val editor = prefs.edit()
                    .putString(AppConstants.KEY_SPOTIFY_ACCESS_TOKEN, accessToken)
                if (!refreshed.refreshToken.isNullOrBlank()) {
                    editor.putString(AppConstants.KEY_SPOTIFY_REFRESH_TOKEN, refreshed.refreshToken)
                }
                if (refreshed.expiresInSec != null && refreshed.expiresInSec > 0) {
                    editor.putLong(AppConstants.KEY_SPOTIFY_EXPIRES_AT, (nowSec + refreshed.expiresInSec))
                }
                editor.apply()
            }
        }

        // Get current track
        var trackId = currentTrackId(accessToken)
        if (trackId == null && !refreshToken.isNullOrBlank() && !clientId.isNullOrBlank()) {
            // 401 retry
            val refreshed = refreshAccessToken(refreshToken, clientId)
            if (refreshed != null && refreshed.accessToken.isNotBlank()) {
                accessToken = refreshed.accessToken
                prefs.edit()
                    .putString(AppConstants.KEY_SPOTIFY_ACCESS_TOKEN, accessToken)
                    .apply()
                trackId = currentTrackId(accessToken)
            }
        }

        if (trackId.isNullOrBlank()) {
            log("Like skipped: no currently playing track")
            playFeedbackTone(success = false)
            return Result.success()
        }

        // Like the track
        val liked = likeTrack(trackId, accessToken)
        playFeedbackTone(success = liked)
        if (liked) {
            log("Liked track: $trackId")
        } else {
            log("Like failed for track: $trackId")
        }

        return Result.success()
    }

    private fun currentTrackId(token: String?): String? {
        if (token.isNullOrBlank()) return null
        val connection = api("https://api.spotify.com/v1/me/player/currently-playing", token, "GET")
        val code = connection.responseCode
        if (code == 204 || code !in 200..299) return null
        val payload = readBody(connection) ?: return null
        val json = JSONObject(payload)
        val id = json.optJSONObject("item")?.optString("id")
        return if (id.isNullOrBlank()) null else id
    }

    private fun likeTrack(trackId: String, token: String?): Boolean {
        if (token.isNullOrBlank()) return false
        val encodedTrackId = URLEncoder.encode(trackId, Charsets.UTF_8.name())
        val connection = api("https://api.spotify.com/v1/me/tracks?ids=$encodedTrackId", token, "PUT")
        return connection.responseCode in 200..299
    }

    private fun refreshAccessToken(refreshToken: String, clientId: String): RefreshedToken? {
        val connection = URL("https://accounts.spotify.com/api/token").openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")

        val body = buildString {
            append("grant_type=refresh_token")
            append("&refresh_token=")
            append(URLEncoder.encode(refreshToken, Charsets.UTF_8.name()))
            append("&client_id=")
            append(URLEncoder.encode(clientId, Charsets.UTF_8.name()))
        }
        OutputStreamWriter(connection.outputStream).use { it.write(body) }

        val statusCode = connection.responseCode
        if (statusCode !in 200..299) return null
        val payload = readBody(connection) ?: return null
        val json = JSONObject(payload)
        val access = json.optString("access_token")
        if (access.isBlank()) return null
        return RefreshedToken(
            accessToken = access,
            refreshToken = json.optString("refresh_token").ifBlank { null },
            expiresInSec = if (json.has("expires_in")) json.optLong("expires_in", 0L).takeIf { it > 0L } else null
        )
    }

    private fun api(url: String, token: String, method: String): HttpURLConnection {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.setRequestProperty("Authorization", "Bearer $token")
        if (method == "PUT") connection.doOutput = true
        return connection
    }

    private fun readBody(connection: HttpURLConnection): String? {
        return try {
            BufferedReader(connection.inputStream.reader()).use { it.readText() }
        } catch (_: Exception) {
            null
        }
    }

    private fun playFeedbackTone(success: Boolean) {
        runCatching {
            val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 100)
            val toneType = if (success) ToneGenerator.TONE_PROP_ACK else ToneGenerator.TONE_PROP_NACK
            tone.startTone(toneType, 180)
            tone.release()
        }
        runCatching {
            @Suppress("DEPRECATION")
            val vibrator: Vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (applicationContext.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
            } else {
                applicationContext.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val effect = if (success) {
                    VibrationEffect.createOneShot(120, VibrationEffect.DEFAULT_AMPLITUDE)
                } else {
                    VibrationEffect.createWaveform(longArrayOf(0, 80, 80, 80), -1)
                }
                vibrator.vibrate(effect)
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(if (success) 120L else 240L)
            }
        }
    }

    private fun log(message: String) {
        val intent = android.content.Intent(AppConstants.ACTION_LOG_EVENT)
            .putExtra(AppConstants.EXTRA_LOG, message)
        androidx.localbroadcastmanager.content.LocalBroadcastManager
            .getInstance(applicationContext)
            .sendBroadcast(intent)
    }

    data class RefreshedToken(
        val accessToken: String,
        val refreshToken: String?,
        val expiresInSec: Long?
    )

    companion object {
        fun enqueue(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = OneTimeWorkRequestBuilder<SpotifyLikeWorker>()
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniqueWork(
                "spotify-like-work",
                ExistingWorkPolicy.REPLACE,
                request
            )
        }
    }
}
