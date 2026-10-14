package br.unip.pm25.ui.detail

import br.unip.pm25.data.ApiJson
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.FakeApi
import br.unip.pm25.data.Health
import br.unip.pm25.data.HourlySeries
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.fixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class DetailViewModelTest {
    private val series = ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json"))
    private val health = ApiJson.decodeFromString<Health>(fixture("health.json"))
    private val requests = mutableListOf<String>()
    private val api = FakeApi(
        onHourly = { id, hours -> requests += "hourly $id $hours"; series },
        onHealth = { id, hours -> requests += "health $id $hours"; health },
    )

    @Before
    fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `abre com as ultimas 24 horas do no pedido`() {
        val vm = DetailViewModel("no-01", DeviceRepository(api))
        assertEquals(DetailData(series, health), vm.state.value.data)
        assertEquals(setOf("hourly no-01 24", "health no-01 24"), requests.toSet())
    }

    @Test
    fun `trocar para 7 dias pede a janela nova`() {
        val vm = DetailViewModel("no-01", DeviceRepository(api))
        requests.clear()
        vm.select(HistoryRange.WEEK)
        assertEquals(HistoryRange.WEEK, vm.state.value.range)
        assertEquals(setOf("hourly no-01 168", "health no-01 168"), requests.toSet())
    }

    @Test
    fun `falha numa das consultas nao mostra dados pela metade`() {
        api.onHealth = { _, _ -> throw IOException() }
        val vm = DetailViewModel("no-01", DeviceRepository(api))
        assertNull(vm.state.value.data)
        assertEquals(LoadError.Network, vm.state.value.error)
    }

    @Test
    fun `falha ao atualizar mantem os dados da mesma janela`() {
        val vm = DetailViewModel("no-01", DeviceRepository(api))
        api.onHourly = { _, _ -> throw IOException() }
        vm.refresh()
        assertEquals(DetailData(series, health), vm.state.value.data)
        assertEquals(LoadError.Network, vm.state.value.error)
    }
}
