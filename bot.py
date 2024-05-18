import logging
import re

from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler

import os
import paramiko
from pathlib import Path
from dotenv import load_dotenv

import psycopg2
from psycopg2 import Error

load_dotenv()
TOKEN = os.getenv('TOKEN')

PATH_TO_LOGFILE = os.getenv('PATH_TO_LOGFILE')
PATH_TO_TEMPFILE = os.getenv('PATH_TO_TEMPFILE')

RM_HOST = os.getenv('RM_HOST')
RM_PORT = os.getenv('RM_PORT')
RM_USER = os.getenv('RM_USER')
RM_PASSWORD = os.getenv('RM_PASSWORD')

DB_DATABASE = os.getenv('DB_DATABASE')

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

DB_REPL_HOST = os.getenv('DB_REPL_HOST')
DB_REPL_PORT = os.getenv('DB_REPL_PORT')
DB_REPL_USER = os.getenv('DB_REPL_USER')
DB_REPL_PASSWORD = os.getenv('DB_REPL_PASSWORD')

# Подключаем логирование
logging.basicConfig(
    filename='logfile.txt', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


def start(update: Update, context):
    user = update.effective_user
    update.message.reply_text(f'Привет, {user.full_name}!')


def helpCommand(update: Update, context):
    update.message.reply_text('Help!')

def echo(update: Update, context):
    update.message.reply_text(update.message.text)

def VerifyPasswordCommand(update: Update, context):
    update.message.reply_text('Введите текст для проверки пароля: ')
    return 'verify_password'

def verify_password(update: Update, context):
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_])[a-zA-Z\d\W_]{8,20}$"
    password =  update.message.text
    if re.match(pattern, password):
        answer="Пароль сложный."
    else:
        answer= "Пароль простой."
    update.message.reply_text(answer)
    return ConversationHandler.END

def ssh_connect(update: Update, command):
    host = RM_HOST
    port = RM_PORT
    username = RM_USER
    password = RM_PASSWORD

    if host and username and password:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(hostname=host, username=username, password=password, port=port)
            stdin, stdout, stderr = client.exec_command(command)
            data = stdout.read() + stderr.read()
            result = str(data).replace('\\n', '\n').replace('\\t', '\t')[2:-1]
            if result:
                return result
            else:
                update.message.reply_text("Результат команды пуст.")
        except paramiko.AuthenticationException as e:
            update.message.reply_text(f"Ошибка аутентификации: {e}")
        except paramiko.SSHException as e:
            update.message.reply_text(f"Ошибка подключения по SSH: {e}")
        finally:
            client.close()
    else:
        update.message.reply_text("Не удалось получить данные для подключения по SSH.")
    return None

def ssh_master_connect(update: Update, file_path):
    load_dotenv()
    dotenv_path = Path('.')  / '.env'
    host = DB_HOST
    port = DB_PORT
    username = DB_USER
    password = DB_PASSWORD



    if host and username and password:
        # Устанавливаем SSH-соединение
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Подключаемся к удаленному серверу
            client.connect(hostname=host, username=username, password=password, port=int(port))
            sftp_client = client.open_sftp()
            # Открываем удаленный файл
            remote_file = sftp_client.open(file_path)
            data = remote_file.read()
            remote_file.close()
            sftp_client.close()
            client.close()
            return data.decode('utf-8')  # Преобразуем байты в строку
        except paramiko.AuthenticationException as e:
            update.message.reply_text(f"Authentication failed: {e}")
        except paramiko.SSHException as e:
            update.message.reply_text(f"SSH connection error: {e}")
        except FileNotFoundError:
            update.message.reply_text(f"File not found on remote server")
    else:
        update.message.reply_text("Не удалось получить данные для подключения по SSH.")
    return None

def db_connect(update: Update):
    host = DB_HOST
    port = DB_PORT
    username = DB_USER
    password = DB_PASSWORD
    database = DB_DATABASE

    connection = None
    cursor = None

    try:
        connection = psycopg2.connect(user=username, password=password, host=host, port=port, database=database)
        cursor = connection.cursor()
        return connection, cursor
    except (Exception, Error) as error:
        if update:
            update.message.reply_text(f"Ошибка при работе с PostgreSQL: {error}")
        else:
            print(f"Ошибка при работе с PostgreSQL: {error}")
        return None, None











def find_emailCommand(update: Update, context):
    update.message.reply_text('Введите текст для поиска Email адресов: ')
    return 'find_email'

def find_email(update: Update, context):
    user_input = update.message.text
    emailRegex = re.compile(r'[\w\.-]+@[\w\.-]+')
    emailList = emailRegex.findall(user_input)

    if not emailList:
        update.message.reply_text('Email адреса не найдены')
        return ConversationHandler.END
    
    emails = ''
    for i, email in enumerate(emailList, 1):
        emails += f'{i}. {email}\n'
    update.message.reply_text(emails)
    context.user_data['email_list'] = emailList
    update.message.reply_text('Хотите сохранить найденные адреса в БД?[Да|нет]: ')
    return 'confirm_save_email'

def confirm_save_email(update: Update, context):
    user_input = update.message.text.lower()
    if user_input == "да":
        if 'email_list' in context.user_data and context.user_data['email_list']:
            try:
                connection, cursor = db_connect(update)
                if connection is not None and cursor is not None:
                    try:
                        with connection, cursor:
                            for email in context.user_data['email_list']:
                                try:
                                    cursor.execute("INSERT INTO email (email) VALUES (%s);", (email,))
                                except Exception as e:
                                    pass
                                connection.commit()                            
                            logging.info("Команда успешно выполнена")
                            update.message.reply_text('Email адреса успешно сохранены в БД.')
                    except (Exception, Error) as error:
                        logging.error("Ошибка при работе с PostgreSQL: %s", error)
                        update.message.reply_text(f"Ошибка при работе с PostgreSQL: {error}")
            except (Exception, Error) as error:
                logging.error("Ошибка при работе с PostgreSQL: %s", error)
                update.message.reply_text(f"Ошибка при работе с PostgreSQL: {error}")
        else:
            update.message.reply_text('Email адреса не найдены.')
    else:
        update.message.reply_text('Email адреса не сохранены.')
    return ConversationHandler.END



def findPhoneNumbersCommand(update: Update, context):
    update.message.reply_text('Введите текст для поиска телефонных номеров: ')

    return 'findPhoneNumbers'


def findPhoneNumbers(update: Update, context):
    user_input = update.message.text

    phoneNumRegex = re.compile(r'\+?\d{1}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{2}[-.\s]?\d{2}')

    phoneNumberList = phoneNumRegex.findall(user_input)

    if not phoneNumberList:
        update.message.reply_text('Телефонные номера не найдены')
        return ConversationHandler.END
    
    phoneNumbers = ''
    for i, phone_number in enumerate(phoneNumberList, 1):
        phoneNumbers += f'{i}. {phone_number}\n'
    
    context.user_data['phone_list'] = phoneNumberList 
    update.message.reply_text(phoneNumbers)
    update.message.reply_text('Хотите сохранить найденные номера в БД?[Да|нет]: ')
    return 'confirm_save_number'

def confirm_save_number(update: Update, context):
    user_input = update.message.text.lower()
    if user_input == "да":
        if 'phone_list' in context.user_data and context.user_data['phone_list']:
            try:
                connection, cursor = db_connect(update)
                if connection is not None and cursor is not None:
                    try:
                        with connection, cursor:
                            for phone_number in context.user_data['phone_list']:
                                try:
                                    cursor.execute("INSERT INTO phone_numbers (phone_numbers) VALUES (%s);", (phone_number,))
                                except Exception as e:
                                    pass
                                connection.commit()   
                            logging.info("Команда успешно выполнена")
                            update.message.reply_text('Номера телефонов успешно сохранены в БД.')
                    except (Exception, Error) as error:
                        logging.error("Ошибка при работе с PostgreSQL: %s", error)
                        update.message.reply_text(f"Ошибка при работе с PostgreSQL: {error}")
            except (Exception, Error) as error:
                logging.error("Ошибка при работе с PostgreSQL: %s", error)
                update.message.reply_text(f"Ошибка при работе с PostgreSQL: {error}")
        else:
            update.message.reply_text('Номера телефонов не найдены.')
    else:
        update.message.reply_text('Номера телефонов не сохранены.')
    return ConversationHandler.END

def get_emails(update: Update, command):
    connection, cursor = db_connect(update)

    if connection is not None and cursor is not None:
        try:
            cursor.execute("SELECT * FROM email;")
            data = cursor.fetchall()
            if data:
                update.message.reply_text('Вот адреса электронных почт, которые удалось найти в моей базе:')
                for row in data:
                    update.message.reply_text(row)
            else:
                update.message.reply_text('Нет данных об адресах электронной почты в базе.')
        except psycopg2.Error as error:
            update.message.reply_text(f"Ошибка при выполнении запроса: {error}")
        finally:
            cursor.close()
            connection.close()
    else:
        update.message.reply_text("Ошибка подключения к базе данных")
    return None




def get_phone_numbers(update: Update, command):
    connection, cursor = db_connect(update)

    if connection is not None and cursor is not None:
        try:
            cursor.execute("SELECT * FROM phone_numbers;")
            data = cursor.fetchall()
            if data:
                update.message.reply_text('Вот номера телефонов, которые удалось найти в моей базе:')
                for row in data:
                    update.message.reply_text(row)
            else:
                update.message.reply_text('Нет данных о номерах телефонов в базе.')
        except psycopg2.Error as error:
            update.message.reply_text(f"Ошибка при выполнении запроса: {error}")
        finally:
            cursor.close()
            connection.close()
    else:
        update.message.reply_text("Ошибка подключения к базе данных")


def get_repl_logs (update: Update, context):
    logging.info('Логи репликации')
    update.message.reply_text("Поиск логов")
   # result= ssh_connect(update, "cat /var/log/postgresql/postgresql-14-main.log | tail -n 15")
    result= ssh_connect(update, 'cat /var/log/postgresql/postgresql-14-main.log | grep "replication"') 
    if result:
        result_lines = result.split('n')

        chunk = ''
        for line in result_lines:
            if len(chunk + line) <= 4000:  # Ограничение по размеру сообщения
                chunk += line + 'n'
            else:
                update.message.reply_text(chunk)
                chunk = line + 'n'
        # Отправляем оставшийся кусочек
        if chunk:
            update.message.reply_text(chunk)
            
    return ConversationHandler.END

 
def helpCommand(update: Update, context):
    update.message.reply_text('Help!  /checkPassword /find_email /findPhoneNumbers /get_release /get_uname /get_uptime /get_df /get_free /get_mpstat /get_w /get_auths /get_critical /get_ps /get_ss /get_apt_list /get_services  /get_emails /get_phone_numbers /get_repl_logs')


def get_release(update: Update, context):
    update.message.reply_text("Версия системы:") 
    result = ssh_connect(update, "lsb_release -a")
    if result:
        update.message.reply_text(result)
    else:
        update.message.reply_text("Не удалось получить информацию о версии системы.")
    return ConversationHandler.END

def get_uname(update: Update, context):
    update.message.reply_text(f'Информация о системе:')
    result = ssh_connect(update, "uname -a")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

def get_uptime(update: Update, context):
    update.message.reply_text(f'Время работы системы:')
    result = ssh_connect(update, "uptime")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

def get_df(update: Update, context):
    update.message.reply_text(f'Сбор информации о состоянии файловой системы:')
    result = ssh_connect(update, "df -h")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

def get_free(update: Update, context):
    update.message.reply_text(f'Сбор информации о состоянии оперативной памяти:')
    result = ssh_connect(update, "free -h")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

def get_mpstat(update: Update, context):
    try:
        update.message.reply_text(f'Сбор информации о производительности системы.')
        result = f'{ssh_connect(update, "uname -a")} \n {ssh_connect(update, "uname -r")} \n {ssh_connect(update, "lscpu")}'
        update.message.reply_text(result)
        if result:
            chunk = ''
            result_lines = result.split(' ')
            for line in result_lines:
                if len(chunk + line) <= 4000:  # Ограничение по размеру сообщения
                    chunk += line 
                else:
                    update.message.reply_text(chunk)
                    chunk = line
        return ConversationHandler.END
    except Exception as e:
        update.message.reply_text(str(e))

def get_w(update: Update, context):
    update.message.reply_text(f'Сбор информации о работающих в данной системе пользователях. ')
    result = ssh_connect(update, "w")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

def get_auths(update: Update, context):
    update.message.reply_text(f'Последние 10 входов в систему.')
    result = ssh_connect(update, "last -10")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

def get_critical(update: Update, context):
    update.message.reply_text(f'Последние 5 критических событий.')
    result = ssh_connect(update, "tail -5 /var/log/syslog")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END

#===
def get_ps(update: Update, context):
    update.message.reply_text('Сбор информации о запущенных процессах.')
    
    result = ssh_connect(update, "ps aux")
    if result:
        result_lines = result.split('n')
        chunk = ''
        for line in result_lines:
            if len(chunk + line) <= 4000:  # Ограничение по размеру сообщения
                chunk += line + 'n'
            else:
                update.message.reply_text(chunk)
                chunk = line + 'n'
        # Отправляем оставшийся кусочек
        if chunk:
            update.message.reply_text(chunk)
            
    return ConversationHandler.END



def get_ss(update: Update, context):
    update.message.reply_text(f'Сбор информации об используемых портах.')
    result = ssh_connect(update, "ss -tuln")
    if result:
        update.message.reply_text(result)
    return ConversationHandler.END


def get_apt_list(update: Update, context):
    update.message.reply_text(f'Сбор информации об установленных пакетах. ')
    psfp5 = update.message.text.split(' ')
    if len(psfp5) > 1:
        i = 1
        command = ''
        while i < len(psfp5):
            command += f'{psfp5[i]} '
            i += 1
        result = ssh_connect(update, f'apt show {command}')
        update.message.reply_text(str(result)[0:100])
    else:
        result = ssh_connect(update, "dpkg --get-selections")
    if result:
        result_lines = result.split('n')
        chunk = ''
        for line in result_lines:
            if len(chunk + line) <= 4000:  # Ограничение по размеру сообщения
                chunk += line + 'n'
            else:
                update.message.reply_text(chunk)
                chunk = line + 'n'
        # Отправляем оставшийся кусочек
        update.message.reply_text(chunk)
    return ConversationHandler.END


 
def FindServiceCommand(update: Update, context):
    update.message.reply_text('Название сервиса: ')
    return 'FindService'
def FindService(update: Update, context):
    
    command =  update.message.text
    result = ssh_connect(update, "dpkg -l | grep "+ command)
    
    update.message.reply_text(result)
    return ConversationHandler.END

def get_services(update: Update, context):
    update.message.reply_text('Сбор информации о запущенных процессах.')
    
    result = ssh_connect(update, "systemctl list-units --type=service --state=running")
    if result:
        result_lines = result.split('n')
        chunk = ''
        for line in result_lines:
            if len(chunk + line) <= 4000:  # Ограничение по размеру сообщения
                chunk += line + 'n'
            else:
                update.message.reply_text(chunk)
                chunk = line + 'n'
        # Отправляем оставшийся кусочек
        if chunk:
            update.message.reply_text(chunk)
            
    return ConversationHandler.END


def main():
    updater = Updater(TOKEN, use_context=True)

    dp = updater.dispatcher

    convHandlerFindPhoneNumbers = ConversationHandler(
        entry_points=[CommandHandler('findPhoneNumbers', findPhoneNumbersCommand)],
        states={
            'findPhoneNumbers': [MessageHandler(Filters.text & ~Filters.command, findPhoneNumbers)],
            'confirm_save_number': [MessageHandler(Filters.text & ~Filters.command, confirm_save_number)]
        },
        fallbacks=[]
    )
    
    convHandlerFindEmail = ConversationHandler(
        entry_points=[CommandHandler('find_email', find_emailCommand)],
        states={
            'find_email': [MessageHandler(Filters.text & ~Filters.command, find_email)],
            'confirm_save_email': [MessageHandler(Filters.text & ~Filters.command, confirm_save_email)]
        },
        fallbacks=[]
    )

    convHandlerVerifyPassword = ConversationHandler(
        entry_points=[CommandHandler('verify_password', VerifyPasswordCommand)],
        states={
            'verify_password': [MessageHandler(Filters.text & ~Filters.command, verify_password)],
        },
        fallbacks=[]
    )
     
    convHandlerFindService = ConversationHandler(
        entry_points=[CommandHandler('FindService', FindServiceCommand)],
        states={
            'FindService': [MessageHandler(Filters.text & ~Filters.command, FindService)],
        },
        fallbacks=[]
    )



    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", helpCommand))
    dp.add_handler(convHandlerFindPhoneNumbers)
    dp.add_handler(convHandlerFindEmail)
    dp.add_handler(convHandlerVerifyPassword)
    dp.add_handler(convHandlerFindService)
        
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    dp.add_handler(CommandHandler("get_release", get_release))
    dp.add_handler(CommandHandler("get_uname", get_uname))
    dp.add_handler(CommandHandler("get_uptime", get_uptime))
    dp.add_handler(CommandHandler("get_df", get_df))
    dp.add_handler(CommandHandler("get_free", get_free))
    dp.add_handler(CommandHandler("get_mpstat", get_mpstat))
    dp.add_handler(CommandHandler("get_w", get_w))
    dp.add_handler(CommandHandler("get_auths", get_auths))
    dp.add_handler(CommandHandler("get_critical", get_critical))
    dp.add_handler(CommandHandler("get_ps", get_ps))
    dp.add_handler(CommandHandler("get_ss", get_ss))
    dp.add_handler(CommandHandler("get_apt_list", get_apt_list))
    dp.add_handler(CommandHandler("get_services", get_services))  

    dp.add_handler(CommandHandler("get_repl_logs", get_repl_logs))

    dp.add_handler(CommandHandler("get_emails", get_emails))
    dp.add_handler(CommandHandler("get_phone_numbers", get_phone_numbers))


    updater.start_polling()

    updater.idle()

if __name__ == '__main__':
    main()
