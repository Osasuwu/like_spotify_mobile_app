package com.example.like_spotify_mobile_app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class BootCompletedReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_LOCKED_BOOT_COMPLETED) {
            return
        }
        val prefs = context.getSharedPreferences(AppConstants.PREFS, Context.MODE_PRIVATE)
        val enabled = prefs.getBoolean(AppConstants.KEY_SERVICE_ENABLED, false)
        if (!enabled) {
            return
        }
        val serviceIntent = Intent(context, MediaButtonForegroundService::class.java).apply {
            action = MediaButtonForegroundService.ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }
}
