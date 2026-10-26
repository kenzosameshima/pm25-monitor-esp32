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
 * O nome do arquivo de `key`. Letras, dígitos, "_" e "-" ficam como estão; qualquer outro caractere vira "~"
 * e o código dele em hexadecimal. Como o próprio "~" também é trocado, duas chaves diferentes nunca dão o
 * mesmo nome ("no.01" e "no_01" davam), e a chave nunca vira um caminho com ".." ou "/".
 */
private fun fileNameFor(key: String): String = buildString {
    for (c in key) {
        if (c in 'A'..'Z' || c in 'a'..'z' || c in '0'..'9' || c == '_' || c == '-') append(c)
        else append("~%04x".format(c.code))
    }
    append(".json")
}

/**
 * Um arquivo por chave em `dir`. A escrita vai para um arquivo temporário e depois o substitui de uma
 * vez, então um desligamento no meio da escrita deixa a versão anterior intacta, nunca um arquivo pela
 * metade.
 */
class FileSnapshotStore(private val dir: File) : SnapshotStore {
    private fun fileFor(key: String) = File(dir, fileNameFor(key))

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
