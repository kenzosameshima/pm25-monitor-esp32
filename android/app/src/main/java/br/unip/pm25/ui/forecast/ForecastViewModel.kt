package br.unip.pm25.ui.forecast

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.Outcome
import br.unip.pm25.data.Timed
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Janela da comparação, a mesma do painel do servidor. */
const val FORECAST_HOURS = 48

/** Como nas outras telas, uma falha mantém a última resposta (desta sessão ou salva), com o aviso do erro. */
data class ForecastUiState(
    val data: Timed<ForecastResponse>? = null,
    val error: LoadError? = null,
    val loading: Boolean = false,
)

class ForecastViewModel(private val deviceId: String, private val repository: DeviceRepository) : ViewModel() {
    private val _state = MutableStateFlow(ForecastUiState(loading = true))
    val state: StateFlow<ForecastUiState> = _state.asStateFlow()
    private var inFlight: Job? = null

    init {
        viewModelScope.launch {
            val saved = repository.cachedForecast(deviceId, FORECAST_HOURS) ?: return@launch
            _state.update { if (it.data == null) it.copy(data = saved) else it }
        }
        refresh()
    }

    fun refresh() {
        if (inFlight?.isActive == true) return
        inFlight = viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            when (val result = repository.forecast(deviceId, FORECAST_HOURS)) {
                is Outcome.Success -> _state.value = ForecastUiState(data = result.value)
                is Outcome.Failure -> _state.update { it.copy(error = result.error, loading = false) }
            }
        }
    }
}
