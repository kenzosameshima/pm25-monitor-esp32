package br.unip.pm25.alerts

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import br.unip.pm25.BuildConfig
import br.unip.pm25.Pm25Application
import br.unip.pm25.data.isLocalNetworkHost
import java.net.URI
import java.util.concurrent.TimeUnit

/**
 * Uma checagem de alertas em segundo plano. Com as notificações desligadas, não consulta nada. Sem
 * internet no celular também não: uma falha nessa hora diria que o servidor caiu quando quem está sem
 * rede é o celular.
 */
class AlertWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val notifier = AlertNotifier(applicationContext)
        if (!notifier.enabled() || !canTellServerFailures(applicationContext)) return Result.success()
        notifier.post((applicationContext as Pm25Application).alertChecker.check())
        return Result.success()
    }
}

/** Agenda as checagens. A cada 15 minutos é o mínimo do WorkManager; o Android pode adiar em economia de bateria. */
object AlertSchedule {
    private const val PERIODIC = "alertas"
    private const val NOW = "alertas-agora"
    private val needsNetwork = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    /** Mantém o agendamento que já existir: abrir o app não reinicia a contagem. */
    fun start(context: Context) {
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC, ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<AlertWorker>(15, TimeUnit.MINUTES).setConstraints(needsNetwork).build(),
        )
    }

    /** Uma checagem já, por exemplo logo depois de o usuário ligar os alertas. */
    fun checkNow(context: Context) {
        WorkManager.getInstance(context).enqueueUniqueWork(
            NOW, ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<AlertWorker>().setConstraints(needsNetwork).build(),
        )
    }
}

/**
 * Se uma falha de consulta agora diz algo sobre o servidor. Pela internet, só com a rede do celular
 * validada (com acesso à internet de fato); na rede local (emulador ou servidor no mesmo Wi-Fi), basta
 * a conexão que o WorkManager já exige.
 */
private fun canTellServerFailures(context: Context): Boolean =
    failuresTellAboutServer(BuildConfig.API_URL) { hasValidatedNetwork(context) }

/** A decisão de `canTellServerFailures`, sem o sistema: `hasValidatedNetwork` só é chamada para um servidor na internet. */
internal fun failuresTellAboutServer(apiUrl: String, hasValidatedNetwork: () -> Boolean): Boolean {
    val host = runCatching { URI(apiUrl).host }.getOrNull().orEmpty()
    return isLocalNetworkHost(host) || hasValidatedNetwork()
}

private fun hasValidatedNetwork(context: Context): Boolean {
    val connectivity = context.getSystemService(ConnectivityManager::class.java) ?: return false
    val capabilities = connectivity.getNetworkCapabilities(connectivity.activeNetwork) ?: return false
    return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
}
