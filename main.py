from datetime import datetime
from pyvirtualdisplay import Display
from selenium.webdriver.common.by import By
import time
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import consul
import os, sys
from elasticsearch import Elasticsearch
import socket
from gevent.threadpool import ThreadPool



show_browser_ui = False

hostname = socket.gethostname()

system_ip = 'localhost'

iteration_pause = 5

returns = 1

if 'TEST_CYCLES' in os.environ:
    returns = int(os.environ['TEST_CYCLES'])

if 'SYSTEM_UNDER_TEST_IP' in os.environ:
    system_ip = os.environ['SYSTEM_UNDER_TEST_IP']

log_path = '/opt/driver/logs'

if 'CHROME_LOGS_PATH' in os.environ:
    log_path = os.environ['CHROME_LOGS_PATH']

es_host = 'localhost:9200'

if 'ES_HOST' in os.environ:
    es_host = os.environ['ES_HOST']


file_path = 'test-url-list.txt'

if 'URL_FILE_PATH' in os.environ:
    file_path = os.environ['URL_FILE_PATH']

if 'ITERATION_PAUSE' in os.environ:
    iteration_pause = int(os.environ['ITERATION_PAUSE'])

if 'SHOW_BROWSER_UI' in os.environ:
    show_browser_ui = os.environ['SHOW_BROWSER_UI'] == "True"


if 'CHROME_LOG_PATH' in os.environ:
    log_path = os.environ['CHROME_LOG_PATH']

maximum_tabs = 5
if 'MAXIMUM_TABS' in os.environ:
    maximum_tabs = int(os.environ['MAXIMUM_TABS'])

es_client = Elasticsearch(hosts=[es_host])

wait_for_elasticsearch = True
es_retries = 200
counter = 1
while wait_for_elasticsearch:
    try:
        es_client.search()
        wait_for_elasticsearch = False
    except Exception, e:
        print e

    if counter < es_retries:
        counter = counter + 1
    else:
        raise Exception("Elasticsearch is not avaliable after " + str(counter) + " retries")
    time.sleep(1)

def make_result_body(i, line, error):
    browsers = fetch_free_browsers()
    print str(datetime.now()) + ' Free browsers: ' + str(len(browsers['free'])) + " Used browsers: " + str(
        len(browsers['used']))
    print str(datetime.now()) + ' ' + str(browsers)

    body = {
        'url': line,
        '@timestamp': datetime.utcnow(),
        'browsers': {
            'free': len(browsers['free']),
            'used': len(browsers['used'])
        },
        'iteration': (i + 1),
        'hostname': hostname
    }

    if error is None:
        body['result'] = 'success'
    else:
        body['result'] = 'failed'
        body['error'] = str(type(error))

    return body


def write_results_to_es(i, line, error):
    try:
        body = make_result_body(i, line, error)
        print es_client.index('soaktest', 'test', body)
    except Exception, ex:
        print ex

cnl = consul.Consul(host=system_ip)

proxy_address = 'http://' + system_ip + ':3128'
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument("--disable-setuid-sandbox")
chrome_options.add_argument('--proxy-server=' + proxy_address)
chrome_options.binary_location = '/opt/google/chrome-beta/google-chrome'


def fetch_free_browsers():
    ss = cnl.agent.services()
    browsers = {
        'free': [],
        'used': []
    }
    for s in ss:
        if ss[s]['Service'] == 'shield-browser':
           if 'free' in ss[s]['Tags']:
               browsers['free'].append(s)
           elif 'used' in  ss[s]['Tags']:
               browsers['used'].append(s)
    return browsers


if not show_browser_ui:
    display = Display(visible=0, size=(800, 600))
    display.start()


desired_capabilities = None


service_log_path = "chromedriver.log"
service_args = ['--verbose', '--log-path=' + log_path + '/' + service_log_path]

pool = ThreadPool(5)

def clear_half_tabs(driver):
    for _ in range(0, int(maximum_tabs / 2)):
        driver.switch_to.window(driver.window_handles[0])
        driver.close()

def run_main_line():
    main_driver = webdriver.Chrome(executable_path='/opt/google/chromedriver', service_args=service_args, chrome_options=chrome_options, desired_capabilities=desired_capabilities)  # usr/lib/chromium-browser/chromedriver')
    try:
        for i in range(0, returns):
            for line in open(file_path, mode='rb'):
                try:
                    #main_driver.get(line)
                    main_driver.execute_script("window.open('%s')" % line.replace("\r\n",''))
                    error = None
                    current_handle = main_driver.window_handles[-1]
                    main_driver.switch_to.window(current_handle)



                    canvas = WebDriverWait(main_driver, 10).until(
                        EC.presence_of_element_located((By.ID, "canvas"))
                    )

                    menu = WebDriverWait(main_driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "nav.context-menu"))
                    )

                    if not canvas:
                        raise Exception('Canvas not found')
                    elif not canvas.__class__.__name__ == 'WebElement':
                        raise Exception('Canvas is not WebElement')

                    if not menu:
                        raise Exception('menu not found')
                    elif not menu.__class__.__name__ == 'WebElement':
                        raise Exception('menu is not WebElement')

                except Exception, e:
                    print e
                    error = e

                try:
                    if len(main_driver.window_handles) >= maximum_tabs:
                        clear_half_tabs(main_driver)
                        current_handle = main_driver.window_handles[-1]
                        main_driver.switch_to.window(current_handle)
                except Exception, e:
                    print e

                pool.spawn(write_results_to_es, i, line, error)

                time.sleep(iteration_pause)
    except Exception as exs:
        print exs
    finally:
        main_driver.quit()


run_main_line()







