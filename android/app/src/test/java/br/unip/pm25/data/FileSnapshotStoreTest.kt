package br.unip.pm25.data

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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
        val names = folder.root.list()!!.sorted()
        assertEquals(2, names.size)
        assertTrue(names.all { it.matches(Regex("[A-Za-z0-9_~-]+\\.json")) })  // nada de ".." nem "/", nem ".tmp"
        assertEquals("b", store.read("../fora"))
        assertFalse(File(folder.root.parentFile, "fora.json").exists())
    }

    @Test
    fun `chaves que so diferem num caractere especial nao dividem o arquivo`() = runTest {
        val store = FileSnapshotStore(folder.root)
        store.write("hourly-no.01-24", "com ponto")
        store.write("hourly-no_01-24", "com sublinhado")
        assertEquals("com ponto", store.read("hourly-no.01-24"))
        assertEquals("com sublinhado", store.read("hourly-no_01-24"))
    }
}
