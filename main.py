"""A simple app to allow adding people to KMs easily

Copyright (c) 2014, Joshua Blake
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation
and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
may be used to endorse or promote products derived from this software without
specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
from bs4 import BeautifulSoup
from flask import Flask, request, render_template
from logging import getLogger
from urllib import urlencode
from urllib2 import urlopen
import re
app = Flask(__name__)
logger = getLogger(__name__)

@app.route('/', methods=['GET', 'POST'])
def main():
    def is_br(url):
        return 'kill_related' in url

    def parse_br(url):
        result = []
        br = BeautifulSoup(urlopen(url).read())
        hostiles = br.find(id='pilots_and_ships').find_all(class_='kb-table')[-1]
        for kill in hostiles.find_all('tr', class_='br-destroyed'):
            href = kill\
                    .find_all('td')[0]\
                    .a\
                    .get('href')
            logger.info('BR contained KM %s', href)
            result.append(href)
        return result

    def add_scouts(kill_url, scouts, password):
        errors = []
        for scout in scouts:
            error_msg = ''
            try:
                data = urlencode((
                    ('scoutname', scout),
                    ('password', password),
                    ('scoutsubmit', 'add pilot'),
                ))

                response = urlopen(kill_url, data=data).read()
            except BaseException as e:
                error_msg = 'Error: ' + str(e)
            else:
                if not scout in response:
                    error = re.search('<b>(Error: .+)</b>', response)
                    if error:
                        error_msg = error.groups(1)[0]
                    else:
                        error_msg = 'Error'
            if error_msg:
                errors.append('{} when adding {} to KM {}'\
                            .format(error_msg, scout, kill_url))
        return errors

    if request.method == 'GET':
        return render_template('form.html')
    elif request.method == 'POST':
        lines = request.form['content'].splitlines()
        kills = []
        pilots = []
        for line in lines:
            logger.debug('parsing %s', line)
            line = line.strip()
            if line.startswith('http'):
                logger.debug('line is url')
                if is_br(line):
                    logger.info('found BR %s', line)
                    kills.extend(parse_br(line))
                else:
                    logger.info('found KM %s', line)
                    kills.append(line)
            else:
                logger.info('found pilot', line)
                pilots.append(line)

        errors = []
        for kill in kills:
            errors.extend(add_scouts(kill, pilots, request.form['password']))
        if errors == []:
            errors = ['success']
        return '<br>'.join(errors)

