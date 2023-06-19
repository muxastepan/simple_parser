import asyncio
import re
from abc import ABC

import aiohttp
from bs4 import BeautifulSoup


class FileManager:
    @staticmethod
    def read_urls(path):
        with open(path, 'r+') as file:
            return file.readlines()

    @staticmethod
    def write_results(path: str, results: str):
        with open(path, 'w+', encoding='utf-8') as file:
            file.write(results)


class Apartment:
    def __init__(self, name: str, price: str, address: str, price_digit: int, url: str):
        self.url = url
        self.address = address
        self.price = price
        self.price_digit = price_digit
        self.name = name

    def __str__(self):
        return f'{self.name}\t{self.price}\t{self.address}\t{self.url}\n'


class Parse(ABC):
    @staticmethod
    def get(soup: BeautifulSoup) -> list[Apartment]:
        '''Static method for getting apartments info from html'''
        pass


class ReMacros:
    @staticmethod
    def delete_spaces(string, tabs=False, breaks=False, spaces=True):
        if tabs:
            string = re.sub(r'\t+', r'', string)
        if breaks:
            string = re.sub(r'\n+', r'', string)
        if spaces:
            string = re.sub(r'\s+', r' ', string)
        string.strip()
        return string


class ParseSutochno(Parse):
    @staticmethod
    def get(site: str):
        soup = BeautifulSoup(site, "html.parser")
        cards = soup.findAll('div', class_='card')
        result = []
        for card in cards:
            raw_name = card.find('a', class_='card-content__object-type')
            name = raw_name.text
            url = raw_name.get('href')
            raw_address = card.find('p', class_='address__text').find('span').text
            address = ReMacros.delete_spaces(raw_address, tabs=True, breaks=True)
            raw_price = re.search(r'(\d+)(.)(\d+)(.)(₽)', card.find('div', class_='price').text)
            price = raw_price.group(1) + ' ' + raw_price.group(3) + ' ' + raw_price.group(5)
            price_digit = int(raw_price.group(1) + raw_price.group(3))
            raw_price_for = card.find('span', class_='price-text').text
            raw_price_for = re.search(r'(\w+)(.)(\w+)', raw_price_for)
            price_for = raw_price_for.group(1) + ' ' + raw_price_for.group(3)

            result.append(Apartment(name, price + ' ' + price_for, address, price_digit, url))
        return result


class ParseTvil(Parse):
    @staticmethod
    def get(site: str):
        soup = BeautifulSoup(site, "html.parser")
        cards = soup.findAll('div', class_='search-result-item search-result-item--b')
        result = []
        for card in cards:
            if card.text == '    ':
                continue
            name = card.find('span', itemprop='name').text
            raw_address = card.find('span', class_='place-wrapper-text').text
            address = ReMacros.delete_spaces(raw_address, breaks=True)
            raw_price = card.find('div', class_='total-price').text
            price = ReMacros.delete_spaces(raw_price, breaks=True)
            raw_price_digit = re.findall(r'(\d+).(\d+)', price)
            avg_price = (int(raw_price_digit[0][0] + raw_price_digit[0][1]) + int(
                raw_price_digit[1][0] + raw_price_digit[1][1])) // 2
            url = card.find('a', class_='title').get('href')
            result.append(Apartment(name, price, address, avg_price, 'https://tvil.ru' + url))
        return result


class ParseKvartirka(Parse):
    @staticmethod
    def get(site: str):
        soup = BeautifulSoup(site, "html.parser")
        cards = soup.findAll('li', class_='flat-card_root__Uuvel flat-list-item_item__Ei9_x flat-list-item_card___MR1H')
        result = []
        for card in cards:
            name = card.find('span', class_='flat-card-info_buildingType__ZNUgY').text
            subway = card.find('span', class_='flat-subway_text__r3OuS')
            raw_address = card.find('span', class_='address_root__tRWWF')
            if subway:
                address = 'Рядом со станцией метро ' + ReMacros.delete_spaces(subway.text, breaks=True)
            else:
                address = ReMacros.delete_spaces(raw_address.text)
            raw_price = card.find('div', class_='price_root__o0FPR').text
            price = ReMacros.delete_spaces(raw_price, breaks=True)
            raw_price_digit = re.search(r'(\d+)', price)
            price_digit = int(raw_price_digit.group(0))
            url = card.find('a', class_='flat-card_link__okzL_').get('href')
            result.append(Apartment(name, price, address, price_digit, url))
        return result


class Parser:

    def __init__(self, urls: list[str]):
        self.urls = urls
        self.apartments = []

    async def _download_site(self, url: str, session: aiohttp.ClientSession):
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    parse_method = self.choose_parser(url)
                    doc = str(await response.text(errors='ignore'))
                    self.apartments.extend(parse_method(doc))
                else:
                    raise aiohttp.ClientError(f'Response returned with status {response.status}')
        except aiohttp.ClientError as exception:
            print(f'Failed to make request at {url}: {exception}')
        except NotImplementedError:
            print(f'This site cannot be parsed: {url}')

    async def get_apartments(self):

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            tasks = []
            for url in self.urls:
                task = asyncio.create_task(self._download_site(url, session))
                tasks.append(task)
            await asyncio.gather(*tasks, return_exceptions=True)

    def choose_parser(self, url: str):
        if re.match(r'https:\/\/.+sutochno.ru\/.*\?from=mainpage', url):
            return ParseSutochno.get
        if re.match(r'https://tvil.ru/city/.+/', url):
            return ParseTvil.get
        if re.match(r'https://kvartirka.com/.+/', url):
            return ParseKvartirka.get
        raise NotImplementedError

    def sort_by_name(self, ascending=True):
        if ascending:
            self.apartments.sort(key=lambda apart: apart.name)
        else:
            self.apartments.sort(key=lambda apart: apart.name, reverse=True)

    def sort_by_price(self, ascending=True):
        if ascending:
            self.apartments.sort(key=lambda apart: apart.price_digit)
        else:
            self.apartments.sort(key=lambda apart: apart.price_digit, reverse=True)

    def __str__(self):
        return 'Имя:\tЦена:\tАдрес:\tURL:\n' + '\n'.join(str(apartment) for apartment in self.apartments)


def asc_or_not(sort_by: callable):
    asc_or_not = input("What type of sort? (a-Ascending, d - Descending)\n")
    while asc_or_not not in ('a', 'd'):
        print('Wrong input try again')
        asc_or_not = input("What type of sort? (a-Ascending, d - Descending)\n")
    if asc_or_not == 'a':
        sort_by()
    else:
        sort_by(ascending=False)


if __name__ == '__main__':
    print('Reading urls.txt')
    urls = FileManager.read_urls('urls.txt')
    parser = Parser(urls)
    print('Getting apartments')
    asyncio.run(parser.get_apartments())
    print('Finished getting apartments')
    sort_question = input("Would you like to sort by name or price? (0-name, 1-price, any button-don't sort)\n")
    if sort_question == '0':
        asc_or_not(parser.sort_by_name)
    elif sort_question == '1':
        asc_or_not(parser.sort_by_price)
    print('Writing results.txt')
    FileManager.write_results('results.txt', str(parser))
