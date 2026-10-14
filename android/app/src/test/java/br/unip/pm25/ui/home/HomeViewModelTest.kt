package br.unip.pm25.ui.home

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceRepository
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.Pm25Api
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
import java.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {
    /** Responde com a próxima ação da fila: uma lista ou uma exceção. */
    private class ScriptedApi(vararg steps: () -> DeviceList) : Pm25Api {
        private val queue = ArrayDeque(steps.toList())
        override suspend fun devices(): DeviceList = queue.removeFirst()()
    }

    private val list = DeviceList(Instant.parse("2026-10-14T12:00:00Z"), 3, 15, emptyList())

    @Before
    fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `falha depois de um sucesso mantem os dados e mostra o erro`() {
        val vm = HomeViewModel(DeviceRepository(ScriptedApi({ list }, { throw IOException() })))
        vm.refresh()
        assertEquals(list, vm.state.value.data)
        assertNull(vm.state.value.error)

        vm.refresh()
        assertEquals(list, vm.state.value.data)
        assertEquals(LoadError.Network, vm.state.value.error)
        assertFalse(vm.state.value.loading)
    }

    @Test
    fun `sucesso depois de uma falha limpa o erro`() {
        val vm = HomeViewModel(DeviceRepository(ScriptedApi({ throw IOException() }, { list })))
        vm.refresh()
        assertNull(vm.state.value.data)
        assertEquals(LoadError.Network, vm.state.value.error)

        vm.refresh()
        assertEquals(list, vm.state.value.data)
        assertNull(vm.state.value.error)
    }
}
