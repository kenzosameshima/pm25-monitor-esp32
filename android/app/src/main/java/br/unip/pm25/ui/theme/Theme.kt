package br.unip.pm25.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import br.unip.pm25.domain.AirQuality

/** Cores do Material You no Android 12+; esquema padrão nas versões anteriores. */
@Composable
fun Pm25Theme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val colors = when {
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (dark) dynamicDarkColorScheme(LocalContext.current) else dynamicLightColorScheme(LocalContext.current)
        dark -> darkColorScheme()
        else -> lightColorScheme()
    }
    MaterialTheme(colorScheme = colors, content = content)
}

/** Cores das faixas, na ordem da CETESB: verde, amarelo, laranja, vermelho e roxo. Fixas nos dois temas. */
fun AirQuality.color(): Color = when (this) {
    AirQuality.BOA -> Color(0xFF2E7D32)
    AirQuality.MODERADA -> Color(0xFFF9A825)
    AirQuality.RUIM -> Color(0xFFEF6C00)
    AirQuality.MUITO_RUIM -> Color(0xFFC62828)
    AirQuality.PESSIMA -> Color(0xFF6A1B9A)
}

/** Texto sobre a cor da faixa com contraste de pelo menos 4,5:1: branco no laranja da Ruim ficaria em ~3:1. */
fun AirQuality.onColor(): Color =
    if (this == AirQuality.MODERADA || this == AirQuality.RUIM) Color.Black else Color.White
