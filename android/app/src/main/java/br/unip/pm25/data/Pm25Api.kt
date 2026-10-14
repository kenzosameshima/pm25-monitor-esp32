package br.unip.pm25.data

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.GET
import java.util.concurrent.TimeUnit

interface Pm25Api {
    @GET("v1/devices")
    suspend fun devices(): DeviceList

    companion object {
        /** Cliente com o token de leitura em todas as requisições. `baseUrl` termina em "/". */
        fun create(baseUrl: String, readToken: String): Pm25Api {
            val http = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .addInterceptor { chain ->
                    chain.proceed(chain.request().newBuilder().header("Authorization", "Bearer $readToken").build())
                }
                .build()
            return Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(http)
                .addConverterFactory(ApiJson.asConverterFactory("application/json".toMediaType()))
                .build()
                .create(Pm25Api::class.java)
        }
    }
}
