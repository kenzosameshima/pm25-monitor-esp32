package br.unip.pm25.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import br.unip.pm25.alerts.AlertNotifier
import br.unip.pm25.alerts.AlertSchedule

/** Se o cartão dos alertas aparece na tela inicial. Ele some quando as notificações estão ligadas. */
@Stable
class AlertsPrompt internal constructor(enabled: Boolean, dismissed: Boolean = false, denied: Boolean = false) {
    internal var enabled by mutableStateOf(enabled)
    internal var dismissed by mutableStateOf(dismissed)
    internal var denied by mutableStateOf(denied)
    val visible: Boolean get() = !enabled && !dismissed

    internal companion object {
        val Saver = listSaver<AlertsPrompt, Boolean>(
            save = { listOf(it.enabled, it.dismissed, it.denied) },
            restore = { AlertsPrompt(it[0], it[1], it[2]) },
        )
    }
}

/**
 * O estado do cartão, conferido de novo sempre que a tela volta ao primeiro plano (o usuário pode ter
 * ligado as notificações nas configurações). Quando elas passam a valer, roda uma checagem na hora.
 */
@Composable
fun rememberAlertsPrompt(): AlertsPrompt {
    val context = LocalContext.current
    val prompt = rememberSaveable(saver = AlertsPrompt.Saver) { AlertsPrompt(AlertNotifier(context).enabled()) }
    LifecycleResumeEffect(prompt) {
        val now = AlertNotifier(context).enabled()
        if (now && !prompt.enabled) AlertSchedule.checkNow(context)
        prompt.enabled = now
        onPauseOrDispose { }
    }
    return prompt
}

/** Explica os alertas e pede a permissão (Android 13 ou mais novo) ou leva às configurações do app. */
@Composable
fun AlertsCard(prompt: AlertsPrompt) {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        prompt.enabled = ok
        prompt.denied = !ok
        if (ok) AlertSchedule.checkNow(context)
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Alertas desligados", style = MaterialTheme.typography.titleSmall, modifier = Modifier.asHeading())
            Text(
                "Com os alertas, o app avisa quando um sensor para de enviar dados, quando a média horária " +
                    "de PM2,5 fica na faixa Ruim ou pior e quando o servidor não responde. A checagem roda " +
                    "a cada 15 minutos ou mais, conforme o Android permitir.",
                style = MaterialTheme.typography.bodySmall,
            )
            if (prompt.denied) {
                Text(
                    "Permissão negada. Para ligar depois: Configurações > Apps > PM2,5 > Notificações.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !prompt.denied) {
                        launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        openNotificationSettings(context)
                    }
                }) { Text(if (prompt.denied) "Abrir configurações" else "Ativar alertas") }
                TextButton(onClick = { prompt.dismissed = true }) { Text("Agora não") }
            }
        }
    }
}

private fun openNotificationSettings(context: Context) {
    context.startActivity(
        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
    )
}
