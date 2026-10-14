package br.unip.pm25

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import br.unip.pm25.ui.LocalNetworkGate
import br.unip.pm25.ui.home.HomeRoute
import br.unip.pm25.ui.home.HomeViewModel
import br.unip.pm25.ui.theme.Pm25Theme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repository = (application as Pm25Application).repository
        setContent {
            Pm25Theme {
                LocalNetworkGate(BuildConfig.API_URL) {
                    val viewModel: HomeViewModel = viewModel(factory = viewModelFactory {
                        initializer { HomeViewModel(repository) }
                    })
                    HomeRoute(viewModel)
                }
            }
        }
    }
}
