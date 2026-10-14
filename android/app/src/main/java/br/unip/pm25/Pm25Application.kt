package br.unip.pm25

import android.app.Application
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.Pm25Api

/** Monta as dependências uma vez por processo; as telas pegam o repositório daqui. */
class Pm25Application : Application() {
    val repository: DeviceRepository by lazy {
        DeviceRepository(Pm25Api.create(BuildConfig.API_URL, BuildConfig.READ_TOKEN))
    }
}
