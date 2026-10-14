package br.unip.pm25.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.Outcome
import br.unip.pm25.data.Timed
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * `data` é a última resposta que deu certo, desta sessão ou salva de uma anterior. Uma falha depois
 * dela não apaga os dados: a tela continua mostrando o que tinha, com o aviso do erro e a hora da
 * última atualização.
 */
data class HomeUiState(
    val data: Timed<DeviceList>? = null,
    val error: LoadError? = null,
    val loading: Boolean = false,
)

class HomeViewModel(private val repository: DeviceRepository) : ViewModel() {
    private val _state = MutableStateFlow(HomeUiState(loading = true))
    val state: StateFlow<HomeUiState> = _state.asStateFlow()
    private var inFlight: Job? = null

    init {
        // A versão salva aparece enquanto a rede responde; se a rede responder antes, ela é descartada.
        viewModelScope.launch {
            val saved = repository.cachedDevices() ?: return@launch
            _state.update { if (it.data == null) it.copy(data = saved) else it }
        }
    }

    /** Busca o estado dos nós; ignora o pedido se já houver uma consulta em andamento. */
    fun refresh() {
        if (inFlight?.isActive == true) return
        inFlight = viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            when (val result = repository.devices()) {
                is Outcome.Success -> _state.value = HomeUiState(data = result.value)
                is Outcome.Failure -> _state.update { it.copy(error = result.error, loading = false) }
            }
        }
    }
}
