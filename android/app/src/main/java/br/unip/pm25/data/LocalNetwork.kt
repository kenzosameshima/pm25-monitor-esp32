package br.unip.pm25.data

/**
 * Verdadeiro se `host` é um endereço da rede local: IPv4 privado ou link-local, IPv6 local (fc00::/7,
 * fe80::/10) ou nome ".local". Loopback não conta. Não consulta DNS: um nome comum vale como internet.
 *
 * A partir do Android 17, falar com esses endereços exige a permissão ACCESS_LOCAL_NETWORK.
 */
fun isLocalNetworkHost(host: String): Boolean {
    val h = host.trim().removePrefix("[").removeSuffix("]").lowercase()
    if (h.endsWith(".local")) return true
    if (':' in h) return h.startsWith("fc") || h.startsWith("fd") || h.startsWith("fe8") ||
        h.startsWith("fe9") || h.startsWith("fea") || h.startsWith("feb")
    val octets = h.split('.').map { it.toIntOrNull() ?: return false }
    if (octets.size != 4 || octets.any { it !in 0..255 }) return false
    val (a, b) = octets
    return a == 10 || (a == 172 && b in 16..31) || (a == 192 && b == 168) || (a == 169 && b == 254)
}
