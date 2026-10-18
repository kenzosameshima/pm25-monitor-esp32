package br.unip.pm25.alerts

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import br.unip.pm25.MainActivity
import br.unip.pm25.R
import br.unip.pm25.domain.Alert

/** Canais e envio das notificações de alerta. */
class AlertNotifier(private val context: Context) {
    private val manager = NotificationManagerCompat.from(context)

    /** Cria (ou atualiza) os canais. Pode ser chamado a cada abertura do app. */
    fun createChannels() {
        manager.createNotificationChannelsCompat(AlertChannel.entries.map {
            val importance = if (it == AlertChannel.AIR) NotificationManagerCompat.IMPORTANCE_HIGH
            else NotificationManagerCompat.IMPORTANCE_DEFAULT
            NotificationChannelCompat.Builder(it.id, importance).setName(it.title).setDescription(it.description).build()
        })
    }

    /** Falso se o usuário não deu a permissão (Android 13 ou mais novo) ou desligou as notificações do app. */
    fun enabled(): Boolean = manager.areNotificationsEnabled()

    fun post(alerts: List<Alert>) {
        if (alerts.isEmpty()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) return
        val open = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        for (alert in alerts) {
            val notice = alert.notice()
            val notification = NotificationCompat.Builder(context, notice.channel.id)
                .setSmallIcon(R.drawable.ic_stat_alert)
                .setContentTitle(notice.title)
                .setContentText(notice.text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(notice.text))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build()
            manager.notify(notice.id, notification)
        }
    }
}
