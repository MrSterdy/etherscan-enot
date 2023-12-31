import asyncio
import random
import re

import pyppeteer

from TempMail import TempMail


def create_inbox():
    tmp = TempMail()
    inbox = tmp.generateInbox()

    return tmp, inbox


def generate_hash():
    return hex(random.getrandbits(48))[2:-1]


async def wait_for_captcha(page):
    # Так как капча от гугла находится в iframe, то её загрузка может занять некоторое время
    await page.waitFor('iframe[title="reCAPTCHA"]')
    # Капчи от гугла всегда имеют префикс "a-" перед названием
    captcha_frame = [x for x in page.frames if x.name.startswith("a-")][0]
    await captcha_frame.waitFor('div.recaptcha-checkbox-border', {'timeout': 0})
    await captcha_frame.click('div.recaptcha-checkbox-border')

    while True:
        checkbox_checked = await captcha_frame.evaluate('''() => {
                const checkbox = document.querySelector('.recaptcha-checkbox')
                return checkbox.classList.contains('recaptcha-checkbox-checked')
            }''')
        if checkbox_checked:
            break
        await asyncio.sleep(1)


def submit_form(page):
    return page.evaluate('''() => {
        const submitButton = document.querySelector('input[type=submit]')
        submitButton.click()
    }''')


async def wait_for_email_verification(tmp: TempMail, inbox):
    # Проверяем почту на новые письма каждую секунду
    while True:
        emails = tmp.getEmails(inbox)
        if len(emails) != 0:
            email = emails[0]
            url = re.findall(r"(https://etherscan.io/confirmemail.*)'>", email.html)[0]
            return url
        await asyncio.sleep(1)


async def get_api_key():
    tmp, inbox = create_inbox()

    username = generate_hash()
    password = generate_hash()

    # Заходим на сайт регистрации
    browser = await pyppeteer.launch({'headless': False})
    register_page = await browser.newPage()
    await register_page.goto('https://etherscan.io/register')

    # Ждём загрузку капчи и её решения пользователем
    await wait_for_captcha(register_page)

    # Заполнение формы
    await register_page.type('#ContentPlaceHolder1_txtUserName', username)
    await register_page.type('#ContentPlaceHolder1_txtEmail', inbox.address)
    await register_page.type('#ContentPlaceHolder1_txtConfirmEmail', inbox.address)
    await register_page.type('#ContentPlaceHolder1_txtPassword', password)
    await register_page.type('#ContentPlaceHolder1_txtPassword2', password)
    await register_page.click('#ContentPlaceHolder1_MyCheckBox')

    await submit_form(register_page)

    verification_page = await browser.newPage()
    await verification_page.goto(await wait_for_email_verification(tmp, inbox))
    await verification_page.waitFor('a[href="/login"]')

    login_page = await browser.newPage()
    # Вот тут то вступает в игру CloudFlare
    await login_page.goto('https://etherscan.io/login', {'timeout': 0})
    await wait_for_captcha(login_page)

    await login_page.type('#ContentPlaceHolder1_txtUserName', username)
    await login_page.type('#ContentPlaceHolder1_txtPassword', password)
    await login_page.click('#ContentPlaceHolder1_chkRemember')

    await submit_form(login_page)

    await login_page.waitForNavigation()

    api_page = await browser.newPage()
    await api_page.goto('https://etherscan.io/myapikey')
    await api_page.click('#ContentPlaceHolder1_addnew')
    await api_page.waitFor('#ContentPlaceHolder1_txtAppName')
    await api_page.type('#ContentPlaceHolder1_txtAppName', generate_hash())

    await submit_form(api_page)

    await api_page.waitForNavigation()

    content = await api_page.content()

    # Ключ имеет вид <span id="a_[КЛЮЧ]">[КЛЮЧ]</span>
    return re.findall(r'id="a_(.*)"', content)[0]


async def scrap():
    api_key = await get_api_key()
    f = open('api_key.txt', 'w')
    f.write(api_key)
    f.close()


def main():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(scrap())


if __name__ == '__main__':
    main()
