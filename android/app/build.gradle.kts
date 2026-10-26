import java.util.Properties

plugins {
    // O Kotlin vem embutido no Android Gradle Plugin 9: não há plugin kotlin-android.
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// URL da API e token de leitura vêm do local.properties, que não vai para o git (ver local.properties.example).
val local = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
val apiUrl = local.getProperty("pm25.apiUrl", "http://10.0.2.2:8000/").let { if (it.endsWith("/")) it else "$it/" }
val readToken = local.getProperty("pm25.readToken", "")

android {
    namespace = "br.unip.pm25"
    compileSdk = 37

    defaultConfig {
        applicationId = "br.unip.pm25"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "API_URL", "\"$apiUrl\"")
        buildConfigField("String", "READ_TOKEN", "\"$readToken\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    sourceSets {
        // Arquivos que o servidor e o app conferem nos testes (shared/air-quality-bands.json).
        getByName("test").resources.directories.add("../../shared")
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.androidx.work.runtime.ktx)
    debugImplementation(libs.androidx.compose.ui.tooling)
    // A atividade vazia em que os testes de interface desenham cada tela (só na versão de depuração).
    debugImplementation(libs.androidx.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)

    // Testes de interface: rodam num emulador ou aparelho (connectedDebugAndroidTest), não na JVM.
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    // O Espresso que o teste do Compose traz sozinho chama InputManager.getInstance(), que o Android 17 não tem mais.
    androidTestImplementation(libs.androidx.test.espresso.core)
}
