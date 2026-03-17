package com.example.like_spotify_mobile_app

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
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL

private const val DEFAULT_ARCHIVE_PLAYLIST_NAME = "Discover Weekly Archive"
private const val DEFAULT_BEST_OF_PLAYLIST_NAME = "Botbotb(Best of the best of the best)"

class SpotifyLikeWorker(
    appContext: Context,
    params: WorkerParameters
) : Worker(appContext, params) {

    override fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)
        var accessToken = prefs.getString(AppConstants.KEY_SPOTIFY_ACCESS_TOKEN, null)
        val refreshToken = prefs.getString(AppConstants.KEY_SPOTIFY_REFRESH_TOKEN, null)
        val clientId = prefs.getString(AppConstants.KEY_SPOTIFY_CLIENT_ID, null)
        val archivePlaylistName = prefs.getString(
            AppConstants.KEY_ARCHIVE_PLAYLIST_NAME,
            DEFAULT_ARCHIVE_PLAYLIST_NAME
        ) ?: DEFAULT_ARCHIVE_PLAYLIST_NAME
        val bestOfPlaylistName = prefs.getString(
            AppConstants.KEY_BEST_OF_PLAYLIST_NAME,
            DEFAULT_BEST_OF_PLAYLIST_NAME
        ) ?: DEFAULT_BEST_OF_PLAYLIST_NAME

        if (accessToken.isNullOrBlank()) {
            log("Like skipped: Spotify access token missing")
            playFeedbackTone(success = false)
            return Result.success()
        }

        var trackInfo = currentTrackInfo(accessToken)
        if (trackInfo.statusCode == 401 && !refreshToken.isNullOrBlank() && !clientId.isNullOrBlank()) {
            val refreshed = refreshAccessToken(refreshToken, clientId)
            if (!refreshed.isNullOrBlank()) {
                accessToken = refreshed
                prefs.edit().putString(AppConstants.KEY_SPOTIFY_ACCESS_TOKEN, accessToken).apply()
                trackInfo = currentTrackInfo(accessToken)
            } else {
                log("Like failed: Spotify token refresh failed")
            }
        }

        val trackId = trackInfo.trackId
        if (trackId.isNullOrBlank()) {
            log("Like skipped: no currently playing track")
            playFeedbackTone(success = false)
            return Result.success()
        }

        val likeResult = likeTrack(trackId, accessToken)
        playFeedbackTone(success = likeResult)
        if (likeResult) {
            log("Liked track: $trackId")

            removeTrackFromArchivePlaylist(trackId, accessToken, archivePlaylistName)

            val trackLikeCount = incrementCountMapValue(AppConstants.KEY_TRACK_LIKE_COUNTS, trackId)
            if (trackLikeCount == 3) {
                addTrackToBestOfPlaylist(trackId, accessToken, bestOfPlaylistName)
            }

            followArtistsWhenGlobalLikedThresholdReached(trackInfo.artistIds, accessToken)
        } else {
            log("Like failed for track: $trackId")
        }
        return Result.success()
    }

    private fun currentTrackInfo(token: String?): TrackInfo {
        if (token.isNullOrBlank()) {
            return TrackInfo(null, emptyList(), 401)
        }
        val connection = api("https://api.spotify.com/v1/me/player/currently-playing", token, "GET")
        val code = connection.responseCode
        if (code == 204) {
            return TrackInfo(null, emptyList(), code)
        }
        val payload = readBody(connection)
        if (code !in 200..299 || payload.isNullOrBlank()) {
            return TrackInfo(null, emptyList(), code)
        }
        val json = JSONObject(payload)
        val item = json.optJSONObject("item")
        val id = item?.optString("id")

        val artistIds = mutableListOf<String>()
        val artists = item?.optJSONArray("artists")
        if (artists != null) {
            for (index in 0 until artists.length()) {
                val artist = artists.optJSONObject(index) ?: continue
                val artistId = artist.optString("id")
                if (artistId.isNotBlank()) {
                    artistIds.add(artistId)
                }
            }
        }

        return TrackInfo(if (id.isNullOrBlank()) null else id, artistIds, code)
    }

    private fun likeTrack(trackId: String, token: String?): Boolean {
        if (token.isNullOrBlank()) {
            return false
        }
        val encodedTrackId = URLEncoder.encode(trackId, Charsets.UTF_8.name())
        val url = "https://api.spotify.com/v1/me/tracks?ids=$encodedTrackId"
        val connection = api(url, token, "PUT")
        val code = connection.responseCode
        return code in 200..299
    }

    private fun refreshAccessToken(refreshToken: String, clientId: String): String? {
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
        if (statusCode !in 200..299) {
            val error = readErrorBody(connection)
            log("Spotify token refresh failed ($statusCode): ${error ?: "<empty>"}")
            return null
        }
        val payload = readBody(connection) ?: return null
        return JSONObject(payload).optString("access_token")
    }

    private fun removeTrackFromArchivePlaylist(trackId: String, token: String?, playlistName: String) {
        if (token.isNullOrBlank() || playlistName.isBlank()) {
            return
        }
        val playlistId = ensurePlaylistId(token, playlistName, createIfMissing = false) ?: run {
            log("Archive playlist '$playlistName' not found, remove skipped")
            return
        }

        val connection = api(
            "https://api.spotify.com/v1/playlists/$playlistId/tracks",
            token,
            "DELETE",
            contentType = "application/json"
        )
        val body = JSONObject()
            .put(
                "tracks",
                JSONArray().put(JSONObject().put("uri", "spotify:track:$trackId"))
            )
            .toString()

        OutputStreamWriter(connection.outputStream).use { it.write(body) }
        val code = connection.responseCode
        if (code in 200..299) {
            log("Removed track from '$playlistName': $trackId")
        } else {
            val error = readErrorBody(connection)
            log("Archive remove failed ($code): ${error ?: "<empty>"}")
        }
    }

    private fun addTrackToBestOfPlaylist(trackId: String, token: String?, playlistName: String) {
        if (token.isNullOrBlank() || playlistName.isBlank()) {
            return
        }
        val playlistId = ensurePlaylistId(token, playlistName, createIfMissing = true) ?: run {
            log("Best-of playlist '$playlistName' unavailable, add skipped")
            return
        }

        val connection = api(
            "https://api.spotify.com/v1/playlists/$playlistId/tracks",
            token,
            "POST",
            contentType = "application/json"
        )
        val body = JSONObject()
            .put("uris", JSONArray().put("spotify:track:$trackId"))
            .toString()

        OutputStreamWriter(connection.outputStream).use { it.write(body) }
        val code = connection.responseCode
        if (code in 200..299) {
            log("Added track to '$playlistName': $trackId")
        } else {
            val error = readErrorBody(connection)
            log("Best-of add failed ($code): ${error ?: "<empty>"}")
        }
    }

    private fun ensurePlaylistId(token: String, playlistName: String, createIfMissing: Boolean): String? {
        findPlaylistIdByName(token, playlistName)?.let { return it }
        if (!createIfMissing) {
            return null
        }

        val userId = currentUserId(token) ?: return null
        val connection = api(
            "https://api.spotify.com/v1/users/$userId/playlists",
            token,
            "POST",
            contentType = "application/json"
        )
        val body = JSONObject()
            .put("name", playlistName)
            .put("public", false)
            .put("description", "Managed by Like Spotify Mobile App")
            .toString()
        OutputStreamWriter(connection.outputStream).use { it.write(body) }

        val code = connection.responseCode
        if (code !in 200..299) {
            val error = readErrorBody(connection)
            log("Playlist create failed ($code): ${error ?: "<empty>"}")
            return null
        }

        val payload = readBody(connection) ?: return null
        val playlistId = JSONObject(payload).optString("id")
        return playlistId.takeIf { it.isNotBlank() }
    }

    private fun findPlaylistIdByName(token: String, playlistName: String): String? {
        val needle = playlistName.trim()
        log("Playlist search: looking for \"$needle\" (${needle.length} chars, codepoints: ${needle.map { it.code }})")
        var offset = 0
        while (true) {
            val connection = api(
                "https://api.spotify.com/v1/me/playlists?limit=50&offset=$offset",
                token,
                "GET"
            )
            val code = connection.responseCode
            if (code !in 200..299) {
                log("Playlist search: API error $code at offset $offset")
                return null
            }

            val payload = readBody(connection) ?: return null
            val json = JSONObject(payload)
            val items = json.optJSONArray("items") ?: return null
            log("Playlist search: page offset=$offset, got ${items.length()} items")
            for (index in 0 until items.length()) {
                val playlist = items.optJSONObject(index) ?: continue
                val rawName = playlist.optString("name")
                val name = rawName.trim()
                if (name.equals(needle, ignoreCase = true)) {
                    val id = playlist.optString("id")
                    if (id.isNotBlank()) {
                        log("Playlist search: found \"$name\" -> $id")
                        return id
                    }
                } else if (name.contains(needle, ignoreCase = true) || needle.contains(name, ignoreCase = true)) {
                    log("Playlist search: close match \"$rawName\" (${rawName.length} chars, codepoints: ${rawName.map { it.code }})")
                }
            }

            if (items.length() < 50) {
                log("Playlist search: exhausted all pages, \"$needle\" not found")
                return null
            }
            offset += 50
        }
    }

    private fun currentUserId(token: String): String? {
        val prefs = applicationContext.getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)
        val cached = prefs.getString(AppConstants.KEY_SPOTIFY_USER_ID, null)
        if (!cached.isNullOrBlank()) {
            return cached
        }

        val connection = api("https://api.spotify.com/v1/me", token, "GET")
        val code = connection.responseCode
        if (code !in 200..299) {
            return null
        }
        val payload = readBody(connection) ?: return null
        val userId = JSONObject(payload).optString("id")
        if (userId.isBlank()) {
            return null
        }
        prefs.edit().putString(AppConstants.KEY_SPOTIFY_USER_ID, userId).apply()
        return userId
    }

    private fun followArtistsWhenGlobalLikedThresholdReached(
        artistIds: List<String>,
        token: String?
    ) {
        if (artistIds.isEmpty() || token.isNullOrBlank()) {
            return
        }

        val globalCounts = loadGlobalLikedArtistCounts(token)
        for (artistId in artistIds.distinct()) {
            val totalLiked = globalCounts[artistId] ?: 0
            if (totalLiked >= 5) {
                followArtistOnSpotify(artistId, token)
            }
        }
    }

    private fun loadGlobalLikedArtistCounts(token: String): Map<String, Int> {
        val counts = mutableMapOf<String, Int>()
        var offset = 0
        while (true) {
            val connection = api(
                "https://api.spotify.com/v1/me/tracks?limit=50&offset=$offset",
                token,
                "GET"
            )
            val code = connection.responseCode
            if (code !in 200..299) {
                val error = readErrorBody(connection)
                log("Failed to load liked tracks ($code): ${error ?: "<empty>"}")
                return counts
            }

            val payload = readBody(connection) ?: return counts
            val root = JSONObject(payload)
            val items = root.optJSONArray("items") ?: return counts
            for (itemIndex in 0 until items.length()) {
                val savedTrack = items.optJSONObject(itemIndex) ?: continue
                val track = savedTrack.optJSONObject("track") ?: continue
                val artists = track.optJSONArray("artists") ?: continue

                for (artistIndex in 0 until artists.length()) {
                    val artist = artists.optJSONObject(artistIndex) ?: continue
                    val artistId = artist.optString("id")
                    if (artistId.isBlank()) {
                        continue
                    }
                    counts[artistId] = (counts[artistId] ?: 0) + 1
                }
            }

            if (items.length() < 50) {
                return counts
            }
            offset += 50
        }
    }

    private fun followArtistOnSpotify(artistId: String, token: String) {
        val encodedArtistId = URLEncoder.encode(artistId, Charsets.UTF_8.name())
        val connection = api(
            "https://api.spotify.com/v1/me/following?type=artist&ids=$encodedArtistId",
            token,
            "PUT"
        )
        val code = connection.responseCode
        if (code in 200..299) {
            log("Artist followed (global liked >= 5): $artistId")
        } else {
            val error = readErrorBody(connection)
            log("Artist follow failed ($code): ${error ?: "<empty>"}")
        }
    }

    private fun incrementCountMapValue(key: String, itemId: String): Int {
        val map = loadCountMap(key)
        val next = (map[itemId] ?: 0) + 1
        map[itemId] = next
        saveCountMap(key, map)
        return next
    }

    private fun loadCountMap(key: String): MutableMap<String, Int> {
        val prefs = applicationContext.getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)
        val raw = prefs.getString(key, null) ?: return mutableMapOf()
        return try {
            val json = JSONObject(raw)
            val result = mutableMapOf<String, Int>()
            val keys = json.keys()
            while (keys.hasNext()) {
                val id = keys.next()
                result[id] = json.optInt(id, 0)
            }
            result
        } catch (_: Exception) {
            mutableMapOf()
        }
    }

    private fun saveCountMap(key: String, map: Map<String, Int>) {
        val prefs = applicationContext.getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)
        val json = JSONObject()
        for ((id, count) in map) {
            json.put(id, count)
        }
        prefs.edit().putString(key, json.toString()).apply()
    }

    private fun api(url: String, token: String, method: String): HttpURLConnection {
        return api(url, token, method, contentType = null)
    }

    private fun api(
        url: String,
        token: String,
        method: String,
        contentType: String?
    ): HttpURLConnection {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.setRequestProperty("Authorization", "Bearer $token")
        if (contentType != null) {
            connection.setRequestProperty("Content-Type", contentType)
        }
        if (method == "POST" || method == "PUT" || method == "DELETE") {
            connection.doOutput = true
        }
        return connection
    }

    private fun readBody(connection: HttpURLConnection): String? {
        return try {
            BufferedReader(connection.inputStream.reader()).use { it.readText() }
        } catch (_: Exception) {
            null
        }
    }

    private fun readErrorBody(connection: HttpURLConnection): String? {
        return try {
            BufferedReader(connection.errorStream?.reader() ?: return null).use { it.readText() }
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

    data class TrackInfo(val trackId: String?, val artistIds: List<String>, val statusCode: Int)

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
