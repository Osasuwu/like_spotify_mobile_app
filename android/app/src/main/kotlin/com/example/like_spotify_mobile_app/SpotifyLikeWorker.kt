package com.example.like_spotify_mobile_app

import android.content.Context
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
import java.net.URL

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
            return Result.success()
        }

        val trackResult = currentTrackId(accessToken)
        if (trackResult.statusCode == 401 && !refreshToken.isNullOrBlank() && !clientId.isNullOrBlank()) {
            val refreshed = refreshAccessToken(refreshToken, clientId)
            if (!refreshed.isNullOrBlank()) {
                accessToken = refreshed
                prefs.edit().putString(AppConstants.KEY_SPOTIFY_ACCESS_TOKEN, accessToken).apply()
            }
        }

        val trackId = currentTrackId(accessToken).trackId
        if (trackId.isNullOrBlank()) {
            log("Like skipped: no currently playing track")
            return Result.success()
        }

        val likeResult = likeTrack(trackId, accessToken)
        if (likeResult) {
            log("Liked track: $trackId")
        } else {
            log("Like failed for track: $trackId")
        }
        return Result.success()
    }

    private fun currentTrackId(token: String?): TrackResult {
        if (token.isNullOrBlank()) {
            return TrackResult(null, 401)
        }
        val connection = api("https://api.spotify.com/v1/me/player/currently-playing", token, "GET")
        val code = connection.responseCode
        if (code == 204) {
            return TrackResult(null, code)
        }
        val payload = readBody(connection)
        if (code !in 200..299 || payload.isNullOrBlank()) {
            return TrackResult(null, code)
        }
        val json = JSONObject(payload)
        val item = json.optJSONObject("item")
        val id = item?.optString("id")
        return TrackResult(if (id.isNullOrBlank()) null else id, code)
    }

    private fun likeTrack(trackId: String, token: String?): Boolean {
        if (token.isNullOrBlank()) {
            return false
        }
        val url = "https://api.spotify.com/v1/me/tracks?ids=$trackId"
        val connection = api(url, token, "PUT")
        val code = connection.responseCode
        return code in 200..299
    }

    private fun refreshAccessToken(refreshToken: String, clientId: String): String? {
        val connection = URL("https://accounts.spotify.com/api/token").openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")

        val body = "grant_type=refresh_token&refresh_token=$refreshToken&client_id=$clientId"
        OutputStreamWriter(connection.outputStream).use { it.write(body) }

        if (connection.responseCode !in 200..299) {
            return null
        }
        val payload = readBody(connection) ?: return null
        return JSONObject(payload).optString("access_token")
    }

    private fun api(url: String, token: String, method: String): HttpURLConnection {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.setRequestProperty("Authorization", "Bearer $token")
        return connection
    }

    private fun readBody(connection: HttpURLConnection): String? {
        return try {
            BufferedReader(connection.inputStream.reader()).use { it.readText() }
        } catch (_: Exception) {
            null
        }
    }

    private fun log(message: String) {
        val intent = android.content.Intent(AppConstants.ACTION_LOG_EVENT)
            .putExtra(AppConstants.EXTRA_LOG, message)
        androidx.localbroadcastmanager.content.LocalBroadcastManager
            .getInstance(applicationContext)
            .sendBroadcast(intent)
    }

    data class TrackResult(val trackId: String?, val statusCode: Int)

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
