package com.example.like_spotify_mobile_app

object AppConstants {
    const val PREFS = "like_spotify_prefs"
    const val KEY_SERVICE_ENABLED = "service_enabled"
    const val KEY_PATTERN = "trigger_pattern"
    const val KEY_WINDOW_MS = "trigger_window_ms"
    const val KEY_DEBOUNCE_MS = "trigger_debounce_ms"

    const val KEY_SPOTIFY_ACCESS_TOKEN = "spotify_access_token"
    const val KEY_SPOTIFY_REFRESH_TOKEN = "spotify_refresh_token"
    const val KEY_SPOTIFY_EXPIRES_AT = "spotify_expires_at"
    const val KEY_SPOTIFY_CLIENT_ID = "spotify_client_id"
    const val KEY_SPOTIFY_USER_ID = "spotify_user_id"

    const val KEY_ARCHIVE_PLAYLIST_NAME = "archive_playlist_name"
    const val KEY_BEST_OF_PLAYLIST_NAME = "best_of_playlist_name"
    const val KEY_TRACK_LIKE_COUNTS = "track_like_counts"
    const val KEY_ARTIST_LIKE_COUNTS = "artist_like_counts"
    const val KEY_TRACKED_ARTIST_IDS = "tracked_artist_ids"

    const val ACTION_MEDIA_EVENT = "com.example.like_spotify_mobile_app.MEDIA_EVENT"
    const val ACTION_LOG_EVENT = "com.example.like_spotify_mobile_app.LOG_EVENT"
    const val ACTION_SERVICE_STATE = "com.example.like_spotify_mobile_app.SERVICE_STATE"

    const val EXTRA_EVENT = "event"
    const val EXTRA_LOG = "log"
    const val EXTRA_ACTIVE = "active"

    const val CHANNEL_SERVICE = "like_spotify_mobile_app/service"
    const val CHANNEL_EVENTS = "like_spotify_mobile_app/events"

    const val NOTIFICATION_CHANNEL_ID = "like_spotify_service"
    const val NOTIFICATION_CHANNEL_NAME = "Like Spotify Listener"
    const val NOTIFICATION_ID = 11001
}
