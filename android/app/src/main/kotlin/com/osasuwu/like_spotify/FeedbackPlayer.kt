package com.osasuwu.like_spotify

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

object FeedbackPlayer {
    fun play(context: Context, success: Boolean) {
        runCatching {
            val tone = ToneGenerator(AudioManager.STREAM_MUSIC, 100)
            val toneType = if (success) ToneGenerator.TONE_PROP_ACK else ToneGenerator.TONE_PROP_NACK
            tone.startTone(toneType, 180)
            tone.release()
        }
        runCatching {
            @Suppress("DEPRECATION")
            val vibrator: Vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
            } else {
                context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
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
}
