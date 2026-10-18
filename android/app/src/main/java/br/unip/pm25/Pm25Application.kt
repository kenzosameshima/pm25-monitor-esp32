package br.unip.pm25

import android.app.Application
import br.unip.pm25.alerts.AlertNotifier
import br.unip.pm25.alerts.AlertSchedule
import br.unip.pm25.data.AlertChecker
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.FileSnapshotStore
import br.unip.pm25.data.Pm25Api
import java.io.File

/** Monta as dependências uma vez por processo; as telas e o worker de alertas pegam daqui. */
class Pm25Application : Application() {
    val repository: DeviceRepository by lazy {
        DeviceRepository(
            Pm25Api.create(BuildConfig.API_URL, BuildConfig.READ_TOKEN),
            // cacheDir: o sistema pode limpar quando faltar espaço, e tudo ali pode ser buscado de novo na API.
            FileSnapshotStore(File(cacheDir, "respostas")),
        )
    }

    val alertChecker: AlertChecker by lazy {
        // filesDir, não cacheDir: se o sistema apagasse o que já foi avisado, os alertas se repetiriam.
        AlertChecker(repository, FileSnapshotStore(File(filesDir, "alertas")))
    }

    override fun onCreate() {
        super.onCreate()
        AlertNotifier(this).createChannels()
        AlertSchedule.start(this)
    }
}
