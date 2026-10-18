package br.unip.pm25.alerts

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Só na versão de depuração: roda uma checagem de alertas na hora, sem esperar o agendamento de 15
 * minutos (o WorkManager ignora uma execução forçada da tarefa periódica antes do horário). Uso:
 *
 *     adb shell am broadcast -n br.unip.pm25/.alerts.CheckNowReceiver
 */
class CheckNowReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) = AlertSchedule.checkNow(context)
}
