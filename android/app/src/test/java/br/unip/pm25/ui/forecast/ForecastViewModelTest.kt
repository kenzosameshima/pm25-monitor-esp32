package br.unip.pm25.ui.forecast

import br.unip.pm25.data.ApiJson
import br.unip.pm25.data.FakeApi
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.InMemorySnapshotStore
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.fixture
import br.unip.pm25.data.repository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class ForecastViewModelTest {
    private val forecast = ApiJson.decodeFromString<ForecastResponse>(fixture("forecast.json"))
    private val store = InMemorySnapshotStore()
    private val requests = mutableListOf<String>()
    private val api = FakeApi(onForecast = { id, hours -> requests += "$id $hours"; forecast })

    @Before
    fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `abre com as ultimas 48 horas do no pedido`() {
        val vm = ForecastViewModel("no-01", repository(api, store))
        assertEquals(forecast, vm.state.value.data?.value)
        assertEquals(listOf("no-01 48"), requests)
    }

    @Test
    fun `falha ao atualizar mantem a ultima comparacao`() {
        val vm = ForecastViewModel("no-01", repository(api, store))
        api.onForecast = { _, _ -> throw IOException() }
        vm.refresh()
        assertEquals(forecast, vm.state.value.data?.value)
        assertEquals(LoadError.Network, vm.state.value.error)
    }

    @Test
    fun `sem rede mostra a comparacao salva`() {
        ForecastViewModel("no-01", repository(api, store))
        api.onForecast = { _, _ -> throw IOException() }
        val reopened = ForecastViewModel("no-01", repository(api, store))
        assertEquals(forecast, reopened.state.value.data?.value)
        assertEquals(LoadError.Network, reopened.state.value.error)
    }
}
