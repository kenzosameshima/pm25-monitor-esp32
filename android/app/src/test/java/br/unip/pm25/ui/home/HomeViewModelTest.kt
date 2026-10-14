package br.unip.pm25.ui.home

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.FakeApi
import br.unip.pm25.data.InMemorySnapshotStore
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.TestClock
import br.unip.pm25.data.repository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.io.IOException
import java.time.Duration
import java.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {
    private val list = DeviceList(Instant.parse("2026-10-14T12:00:00Z"), 3, 15, emptyList())
    private val newer = list.copy(generatedAt = Instant.parse("2026-10-15T09:00:00Z"))
    private val store = InMemorySnapshotStore()
    private val clock = TestClock()

    /** Cada consulta responde com o próximo passo da fila: uma lista ou uma exceção. */
    private fun viewModelAnswering(vararg steps: () -> DeviceList): HomeViewModel {
        val queue = ArrayDeque(steps.toList())
        return HomeViewModel(repository(FakeApi(onDevices = { queue.removeFirst()() }), store, clock))
    }

    @Before
    fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `falha depois de um sucesso mantem os dados e mostra o erro`() {
        val vm = viewModelAnswering({ list }, { throw IOException() })
        vm.refresh()
        assertEquals(list, vm.state.value.data?.value)
        assertNull(vm.state.value.error)

        vm.refresh()
        assertEquals(list, vm.state.value.data?.value)
        assertEquals(LoadError.Network, vm.state.value.error)
        assertFalse(vm.state.value.loading)
    }

    @Test
    fun `sucesso depois de uma falha limpa o erro`() {
        val vm = viewModelAnswering({ throw IOException() }, { list })
        vm.refresh()
        assertNull(vm.state.value.data)
        assertEquals(LoadError.Network, vm.state.value.error)

        vm.refresh()
        assertEquals(list, vm.state.value.data?.value)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `app reaberto sem rede mostra a resposta salva, com a hora em que chegou`() {
        viewModelAnswering({ list }).refresh()
        val receivedAt = clock.now
        clock.advance(Duration.ofHours(20))

        val reopened = viewModelAnswering({ throw IOException() })
        assertEquals(list, reopened.state.value.data?.value)     // aparece antes da rede responder
        reopened.refresh()
        assertEquals(list, reopened.state.value.data?.value)
        assertEquals(receivedAt, reopened.state.value.data?.receivedAt)
        assertEquals(LoadError.Network, reopened.state.value.error)
    }

    @Test
    fun `resposta da rede substitui a salva`() {
        viewModelAnswering({ list }).refresh()
        val reopened = viewModelAnswering({ newer })
        reopened.refresh()
        assertEquals(newer, reopened.state.value.data?.value)
    }
}
