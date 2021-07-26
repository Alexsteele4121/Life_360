from bs4 import BeautifulSoup
import concurrent.futures
import threading
import requests_html
import json
import time

LoginURL = 'https://www.life360.com/v3/oauth2/token.json'
CirclesUrl = 'https://www.life360.com/v3/circles/'


class Tracker:

    def __init__(self, username, password, phoneNumber=True, session=None, keepUpdated=True, updateDelay=5):
        self.username = username
        self.password = password
        self.phoneNumber = phoneNumber
        self.connected = True
        self.loggedIn = False
        if session:
            self.session = session
        else:
            self.session = NewSession()
        if not self.session:
            self.connected = False
        if self.connected:
            self.authorization = gatherAuth(self.session, username, password, self.phoneNumber)
            if not self.authorization:
                print('Not Authorized....')
            else:
                self.loggedIn = True
                self.circles = circleInfo(self.session, self.authorization)
                if not self.circles:
                    self.connected = False
                self.circleCount = len(self.circles)
        self.keepUpdated = keepUpdated
        self.updateLocations()
        if self.keepUpdated:
            threading.Thread(target=self.continuousUpdate, args=[updateDelay, ]).start()

    def updateLocations(self):
        for circle in range(self.circleCount):
            members = memberInfo(self.session, self.circles[circle]['id'], self.authorization)
            if members:
                if 'members' in self.circles[circle]:
                    del self.circles[circle]['members']
                self.circles[circle]['members'] = members

    def continuousUpdate(self, updateDelay):
        while self.keepUpdated:
            self.updateLocations()
            time.sleep(updateDelay)

    def listAllMembers(self):
        data = []
        for circle in self.circles:
            for members in circle['members']:
                data.append(members['name'])
        return data

    def findMembersByName(self, members):
        data = []
        if not isinstance(members, list):
            members = [members]
        for circle in self.circles:
            for memberData in circle['members']:
                for member in members:
                    if member.lower() in memberData['name'].lower():
                        if memberData not in data:
                            data.append(memberData)
        return data

    def findMemberByEmail(self, email):
        pass

    def currentLocation(self, members):
        memberData = self.findMembersByName(members)
        data = []
        for member in memberData:
            data.append([member['name'], member['address'], member['since']])
        return data

    def hasMemberMoved(self, locationTags):
        data = []
        for tag in locationTags:
            memberData = self.findMembersByName(tag[0])[0]
            if memberData['since'] != tag[2]:
                data.append((tag[0], True))
            else:
                data.append((tag[0], False))
        return data

    def distanceBetweenUsers(self, members: list):
        memberData = self.findMembersByName(members)
        data = []
        for member in range(len(members)):
            for secondMember in range(member, len(members)):
                if member is not secondMember:
                    data.append([memberData[member]['name'], memberData[secondMember]['name'],
                                 (memberData[member]['latLng'], memberData[secondMember]['latLng'])])
        latLng = []
        for x in range(len(data)):
            latLng.append(data[x][2])
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(distance, self.session, member1, member2) for member1, member2 in latLng]
            for x in range(len(results)):
                data[x][2] = results[x].result()
        return data

    def distanceFromLatLng(self, members, latlng):
        memberData = self.findMembersByName(members)
        data = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(distance, self.session, member['latLng'], latlng) for member in memberData]
            for x, r in enumerate(results):
                data.append((memberData[x]['name'], r.result()))
        return data


def NewSession():
    return requests_html.HTMLSession()


def Soup(html):
    return BeautifulSoup(html, 'lxml')


def gatherAuth(session, username, password, phone=True):
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US, en;q=0.9',
        'Authorization': 'Basic U3dlcUFOQWdFVkVoVWt1cGVjcmVrYXN0ZXFhVGVXckFTV2E1dXN3MzpXMnZBV3JlY2hhUHJlZG'
                         'FoVVJhZ1VYYWZyQW5hbWVqdQ==',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': "www.life360.com",
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/79.0.3945.130 Safari/537.36"
    }
    if phone:
        load = {
            'countryCode': '1',
            'phone': username,
            'password': password,
            'grant_type': 'password'
        }
    else:
        return None

    if not session:
        session = NewSession()

    try:
        result = session.post(LoginURL, data=load, headers=headers, timeout=5)
    except Exception as e:
        print(e)
        return None
    if not result.ok:
        return None

    webPage = Soup(result.text)
    data = json.loads(webPage.p.text)
    authorization = data['token_type'] + ' ' + data['access_token']
    return authorization


def circleInfo(session, auth):
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
                  ',application/signed-exchange;v=b3;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US, en;q=0.9',
        'Authorization': auth,
        'Connection': 'keep-alive',
        'Host': 'www.life360.com',
        'Referer': 'https://www.life360.com/circles/'
    }

    try:
        result = session.get(CirclesUrl, headers=headers, timeout=5)
    except Exception as e:
        print(e)
        return None

    if not result.ok:
        return None
    else:
        webPage = Soup(result.text)
        data = json.loads(webPage.p.text)
        circles = data['circles']
        ids = []
        for circle in circles:
            ids.append({'id': circle['id'], 'name': circle['name'], 'memberCount': circle['memberCount']})
        return ids


def memberInfo(session, circle, auth):
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
                  ',application/signed-exchange;v=b3;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US, en;q=0.9',
        'Authorization': auth,
        'Connection': 'keep-alive',
        'Host': 'www.life360.com',
        'Referer': 'https://www.life360.com/circles/'
    }

    try:
        result = session.get(CirclesUrl + circle, headers=headers, timeout=5)
    except Exception as e:
        print(e)
        return None

    if not result.ok:
        return None

    webPage = Soup(result.text)
    data = json.loads(webPage.p.text)
    members = data['members']
    users = []
    for member in members:
        users.append({
            'name': member['firstName'] + ' ' + member['lastName'],
            'phone': member['communications'][0]['value'],
            'email': member['communications'][1]['value'],
            'disconnected': member['issues']['disconnected'],
            'latLng': (member['location']['latitude'], member['location']['longitude']),
            'since': time.ctime(member['location']['since']),
            'address': member['location']['address1'],
            'battery': member['location']['battery'],
            'charging': member['location']['charge'],
            'wifi': member['location']['wifiState'],
            'speed': member['location']['speed'],
            'driving': member['location']['isDriving']
        })
    return users


def distance(session, member1, member2):

    webPage = session.get(f'https://www.google.com/search?q=directions+from'
                          f'+{member1[0]}%2C{member1[1]}+to+{member2[0]}%2C{member2[1]}')
    result = Soup(webPage.text)
    dist = result.find('div', class_='BbbuR uc9Qxb uE1RRc')
    if not dist:
        return 0
    dist = dist.text.split()[0]
    try:
        dist = int(dist)
    except Exception as e:
        print(e)
        return 0
    return dist


def main():
    Data = Tracker('YourPhoneNumber', 'YourPassword', keepUpdated=False)
    print(Data.findMembersByName(Data.listAllMembers()))


if __name__ == '__main__':
    main()
