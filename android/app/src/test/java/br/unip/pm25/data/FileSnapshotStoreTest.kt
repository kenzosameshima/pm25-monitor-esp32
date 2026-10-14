package br.unip.pm25.data

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class FileSnapshotStoreTest {
    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun `grava, substitui e le de volta`() = runTest {
        val dir = File(folder.root, "respostas")  // ainda não existe: a primeira escrita cria
        val store = FileSnapshotStore(dir)
        assertNull(store.read("devices"))
        store.write("devices", "um")
        store.write("devices", "dois")
        assertEquals("dois", FileSnapshotStore(dir).read("devices"))
    }

    @Test
    fun `nao deixa arquivo temporario nem usa a chave crua como caminho`() = runTest {
        val store = FileSnapshotStore(folder.root)
        store.write("hourly-no-01-24", "a")
        store.write("../fora", "b")
        assertEquals(listOf("___fora.json", "hourly-no-01-24.json"), folder.root.list()!!.sorted())
        assertEquals("b", store.read("../fora"))
    }
}
