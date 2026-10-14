package br.unip.pm25

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.ui.LocalNetworkGate
import br.unip.pm25.ui.detail.DetailRoute
import br.unip.pm25.ui.detail.DetailViewModel
import br.unip.pm25.ui.forecast.ForecastRoute
import br.unip.pm25.ui.forecast.ForecastViewModel
import br.unip.pm25.ui.home.HomeRoute
import br.unip.pm25.ui.home.HomeViewModel
import br.unip.pm25.ui.theme.Pm25Theme
import kotlinx.serialization.Serializable

/** Destinos da navegação. Cada tela tem o próprio ViewModel, que vive enquanto ela está na pilha. */
@Serializable
private object Home

@Serializable
private data class Detail(val deviceId: String, val location: String? = null)

@Serializable
private data class Forecast(val deviceId: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repository = (application as Pm25Application).repository
        setContent {
            Pm25Theme {
                LocalNetworkGate(BuildConfig.API_URL) { AppNavigation(repository) }
            }
        }
    }
}

@Composable
private fun AppNavigation(repository: DeviceRepository) {
    val navController = rememberNavController()
    NavHost(navController, startDestination = Home) {
        composable<Home> {
            val viewModel: HomeViewModel = viewModel(factory = viewModelFactory {
                initializer { HomeViewModel(repository) }
            })
            HomeRoute(viewModel, onOpenDevice = { navController.navigate(Detail(it.deviceId, it.location)) })
        }
        composable<Detail> { entry ->
            val destination = entry.toRoute<Detail>()
            val viewModel: DetailViewModel = viewModel(factory = viewModelFactory {
                initializer { DetailViewModel(destination.deviceId, repository) }
            })
            DetailRoute(viewModel, destination.deviceId, destination.location, onBack = { navController.popBackStack() },
                onOpenForecast = { navController.navigate(Forecast(destination.deviceId)) })
        }
        composable<Forecast> { entry ->
            val destination = entry.toRoute<Forecast>()
            val viewModel: ForecastViewModel = viewModel(factory = viewModelFactory {
                initializer { ForecastViewModel(destination.deviceId, repository) }
            })
            ForecastRoute(viewModel, destination.deviceId, onBack = { navController.popBackStack() })
        }
    }
}
