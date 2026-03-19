package com.example.like_spotify_mobile_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.view.KeyEvent
import android.support.v4.media.session.MediaSessionCompat
import androidx.core.app.NotificationCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager

class MediaButtonForegroundService : Service() {
    private lateinit var mediaSession: MediaSessionCompat
    private lateinit var detector: MediaEventPatternDetector
    private var nextToggleIsPause = true

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        SpotifyLikeWorker.enqueueWeeklyArchiveSync(this)

        detector = MediaEventPatternDetector(
            windowMsProvider = { prefs().getLong(AppConstants.KEY_WINDOW_MS, 1000L) },
            debounceMsProvider = { prefs().getLong(AppConstants.KEY_DEBOUNCE_MS, 650L) },
            patternProvider = { loadPattern() }
        )

        mediaSession = MediaSessionCompat(this, "LikeSpotifySession").apply {
            setFlags(
                MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS or
                    MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS
            )
            val mediaButtonIntent = Intent(Intent.ACTION_MEDIA_BUTTON).apply {
                setClass(this@MediaButtonForegroundService, MediaButtonReceiver::class.java)
            }
            val mediaButtonPendingIntent = PendingIntent.getBroadcast(
                this@MediaButtonForegroundService,
                4,
                mediaButtonIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            setMediaButtonReceiver(mediaButtonPendingIntent)
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() {
                    onMediaEvent("play")
                }

                override fun onPause() {
                    onMediaEvent("pause")
                }
            })
            isActive = true
        }

        startForeground(AppConstants.NOTIFICATION_ID, buildNotification(active = true))
        sendServiceState(true)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> stopSelfSafely()
            ACTION_EXTERNAL_MEDIA_EVENT -> {
                val rawEvent = intent.getStringExtra(AppConstants.EXTRA_EVENT)
                val event = normalizeExternalEvent(rawEvent)
                if (event != null) {
                    log("External media event: $rawEvent -> $event")
                    onMediaEvent(event)
                }
            }
            ACTION_START, null -> {
                startForeground(AppConstants.NOTIFICATION_ID, buildNotification(active = true))
                sendServiceState(true)
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        mediaSession.isActive = false
        mediaSession.release()
        sendServiceState(false)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun onMediaEvent(event: String) {
        broadcastMediaEvent(event)
        if (detector.onEvent(event, System.currentTimeMillis())) {
            log("Trigger matched: ${loadPattern().joinToString(" -> ")}")
            SpotifyLikeWorker.enqueue(this)
        }
    }

    private fun normalizeExternalEvent(event: String?): String? {
        return when (event) {
            "play" -> "play"
            "pause" -> "pause"
            "toggle" -> {
                val mapped = if (nextToggleIsPause) "pause" else "play"
                nextToggleIsPause = !nextToggleIsPause
                mapped
            }
            else -> null
        }
    }

    private fun broadcastMediaEvent(event: String) {
        val intent = Intent(AppConstants.ACTION_MEDIA_EVENT).putExtra(AppConstants.EXTRA_EVENT, event)
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun sendServiceState(active: Boolean) {
        prefs().edit().putBoolean(AppConstants.KEY_SERVICE_ENABLED, active).apply()
        val intent = Intent(AppConstants.ACTION_SERVICE_STATE).putExtra(AppConstants.EXTRA_ACTIVE, active)
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun loadPattern(): List<String> {
        val raw = prefs().getString(AppConstants.KEY_PATTERN, "pause,play") ?: "pause,play"
        return raw.split(',').map { it.trim() }.filter { it.isNotEmpty() }
    }

    private fun log(message: String) {
        val intent = Intent(AppConstants.ACTION_LOG_EVENT).putExtra(AppConstants.EXTRA_LOG, message)
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun buildNotification(active: Boolean): Notification {
        val stopIntent = Intent(this, MediaButtonForegroundService::class.java).apply {
            action = ACTION_STOP
        }
        val stopPendingIntent = PendingIntent.getService(
            this,
            2,
            stopIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val openIntent = packageManager.getLaunchIntentForPackage(packageName)
        val openPendingIntent = PendingIntent.getActivity(
            this,
            3,
            openIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return NotificationCompat.Builder(this, AppConstants.NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Like Spotify is ${if (active) "active" else "inactive"}")
            .setContentText("Listening for headset pattern")
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setOngoing(true)
            .setSilent(true)
            .addAction(0, "Stop", stopPendingIntent)
            .setContentIntent(openPendingIntent)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val channel = NotificationChannel(
            AppConstants.NOTIFICATION_CHANNEL_ID,
            AppConstants.NOTIFICATION_CHANNEL_NAME,
            NotificationManager.IMPORTANCE_LOW
        )
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    private fun stopSelfSafely() {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun prefs() = getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)

    companion object {
        const val ACTION_START = "ACTION_START"
        const val ACTION_STOP = "ACTION_STOP"
        const val ACTION_EXTERNAL_MEDIA_EVENT = "ACTION_EXTERNAL_MEDIA_EVENT"

        fun dispatchExternalMediaEvent(context: Context, event: String) {
            val serviceIntent = Intent(context, MediaButtonForegroundService::class.java).apply {
                action = ACTION_EXTERNAL_MEDIA_EVENT
                putExtra(AppConstants.EXTRA_EVENT, event)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
        }
    }
}
