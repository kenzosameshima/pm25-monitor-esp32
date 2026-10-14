package br.unip.pm25.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.Health
import br.unip.pm25.data.HourlySeries
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.Outcome
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class HistoryRange(val hours: Int, val label: String) {
    DAY(24, "24 horas"),
    WEEK(168, "7 dias"),
}

data class DetailData(val series: HourlySeries, val health: Health)

/** Como na tela inicial, uma falha mantém os dados anteriores da mesma janela, com o aviso do erro. */
data class DetailUiState(
    val range: HistoryRange = HistoryRange.DAY,
    val data: DetailData? = null,
    val error: LoadError? = null,
    val loading: Boolean = false,
)

class DetailViewModel(private val deviceId: String, private val repository: DeviceRepository) : ViewModel() {
    private val _state = MutableStateFlow(DetailUiState(loading = true))
    val state: StateFlow<DetailUiState> = _state.asStateFlow()
    private var inFlight: Job? = null

    init {
        refresh()
    }

    /** Troca a janela. Os dados da janela anterior saem da tela, para não serem lidos como da nova. */
    fun select(range: HistoryRange) {
        if (range == _state.value.range) return
        inFlight?.cancel()
        _state.value = DetailUiState(range = range)
        refresh()
    }

    fun refresh() {
        if (inFlight?.isActive == true) return
        val range = _state.value.range
        inFlight = viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            when (val result = load(range)) {
                is Outcome.Success -> _state.value = DetailUiState(range = range, data = result.value)
                is Outcome.Failure -> _state.update { it.copy(error = result.error, loading = false) }
            }
        }
    }

    /** Histórico e saúde da coleta em paralelo; a tela só troca de dados quando os dois chegam. */
    private suspend fun load(range: HistoryRange): Outcome<DetailData> = coroutineScope {
        val series = async { repository.hourly(deviceId, range.hours) }
        val health = async { repository.health(deviceId, range.hours) }
        val s = series.await()
        val h = health.await()
        when {
            s is Outcome.Failure -> s
            h is Outcome.Failure -> h
            else -> Outcome.Success(DetailData((s as Outcome.Success).value, (h as Outcome.Success).value))
        }
    }
}
