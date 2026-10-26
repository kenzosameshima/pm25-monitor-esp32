package br.unip.pm25.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import br.unip.pm25.data.isLocalNetworkHost
import java.net.URI

/** Android 17 (API 37) bloqueia a rede local para apps que não têm ACCESS_LOCAL_NETWORK. */
private const val LOCAL_NETWORK_API = 37

private fun hostOf(apiUrl: String): String = runCatching { URI(apiUrl).host }.getOrNull().orEmpty()

private fun needsLocalNetworkPermission(context: Context, apiUrl: String): Boolean =
    Build.VERSION.SDK_INT >= LOCAL_NETWORK_API && isLocalNetworkHost(hostOf(apiUrl)) &&
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_LOCAL_NETWORK) !=
        PackageManager.PERMISSION_GRANTED

/**
 * Mostra `content` quando o app pode falar com a API. Se a API está na rede local (o computador visto
 * do emulador, ou um servidor na mesma rede Wi-Fi) e o Android exige permissão, explica o motivo e a
 * pede antes. Pela URL pública do túnel a permissão não é necessária e nada é pedido.
 */
@Composable
fun LocalNetworkGate(apiUrl: String, content: @Composable () -> Unit) {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(!needsLocalNetworkPermission(context, apiUrl)) }
    var denied by rememberSaveable { mutableStateOf(false) }  // sobrevive a girar a tela; `granted` é conferida de novo
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        granted = ok
        denied = !ok
    }
    if (granted || Build.VERSION.SDK_INT < LOCAL_NETWORK_API) {
        content()
        return
    }
    Surface(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Acesso à rede local", style = MaterialTheme.typography.titleLarge, modifier = Modifier.asHeading())
            Text(
                "O servidor configurado (${hostOf(apiUrl)}) está na rede local. A partir do Android 17, " +
                    "o app só consegue falar com ele com a sua permissão. O app não procura outros " +
                    "aparelhos na rede: ele só consulta esse servidor.",
                style = MaterialTheme.typography.bodyMedium,
            )
            if (denied) {
                Text(
                    "Permissão negada. Para liberar: Configurações > Apps > PM2,5 > Permissões > " +
                        "Dispositivos próximos.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
                OutlinedButton(onClick = {
                    context.startActivity(
                        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                    )
                }) { Text("Abrir configurações") }
            }
            Button(onClick = { launcher.launch(Manifest.permission.ACCESS_LOCAL_NETWORK) }) { Text("Permitir") }
        }
    }
}
