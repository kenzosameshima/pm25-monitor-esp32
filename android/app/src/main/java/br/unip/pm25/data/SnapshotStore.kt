package br.unip.pm25.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** Guarda a última resposta de cada rota, como texto, para o app abrir com dados mesmo sem rede. */
interface SnapshotStore {
    /** O texto salvo para `key`, ou null se não houver ou não der para ler. */
    suspend fun read(key: String): String?

    /** Substitui o texto de `key`. Uma falha de escrita é ignorada: o cache é só uma conveniência. */
    suspend fun write(key: String, text: String)
}

/**
 * Um arquivo por chave em `dir`. A escrita vai para um arquivo temporário e depois o substitui de uma
 * vez, então um desligamento no meio da escrita deixa a versão anterior intacta, nunca um arquivo pela
 * metade.
 */
class FileSnapshotStore(private val dir: File) : SnapshotStore {
    private fun fileFor(key: String) = File(dir, key.replace(Regex("[^A-Za-z0-9_-]"), "_") + ".json")

    override suspend fun read(key: String): String? = withContext(Dispatchers.IO) {
        try {
            fileFor(key).takeIf { it.isFile }?.readText()
        } catch (e: IOException) {
            null
        }
    }

    override suspend fun write(key: String, text: String) {
        withContext(Dispatchers.IO) {
            try {
                dir.mkdirs()
                val target = fileFor(key)
                val temp = File(dir, target.name + ".tmp")
                temp.writeText(text)
                Files.move(temp.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
            } catch (e: IOException) {
                // Sem espaço ou sem permissão: o app segue funcionando, só não terá esta resposta offline.
            }
        }
    }
}
