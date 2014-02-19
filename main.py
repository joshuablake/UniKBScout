"""A simple app to allow adding people to KMs easily

Copyright (c) 2014, Joshua Blake
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
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
from datetime import datetime
from flask import Flask, request, render_template
from urllib import urlencode
from urllib2 import urlopen
import re
app = Flask(__name__)
logger = app.logger
MAX_RUN_TIME = 50  # time in secs to run before quiting for resubmission

#Google AppEnginge times out long requests unless specificallly told otherwise
#KB can be slow so we manually raise this limit to the max possible
try:
    from google.appengine.api import urlfetch
except ImportError:
    pass
else:
    urlfetch.set_default_fetch_deadline(60)


@app.route('/', methods=['GET', 'POST'])
def main():
    """Only external endpoint"""
    if request.method == 'GET':
        return render_template('form.html')

    start_time = datetime.now()
    submission = request.form['content'].splitlines()

    kills = []
    pilots = []
    for line in submission:
        line = line.strip()
        if line.startswith('http'):
            logger.debug('line is url')
            kills.extend(parse_url(line))
        else:
            logger.info('line is pilot %s', line)
            pilots.append(line)

    errors = []
    data = ''
    timed_out = False
    for i, kill in enumerate(kills):
        if out_of_time(start_time):
            data = construct_data(kills[i:], pilots)
            timed_out = True
            break
        errors.extend(add_scouts(kill, pilots, request.form['password']))

    message = create_message(errors, timed_out)
    return render_template('form.html', data=data, message=message)


def parse_url(url):
    """Parse a url and return a list of all KMs"""
    def is_br(url):
        """Check if the url is a BR"""
        return 'kill_related' in url

    if is_br(url):
        logger.info('found BR %s', url)
        return parse_br(url)
    else:
        logger.info('found KM %s', url)
        return [url]

    def parse_br(url):
        """Get all KMs on a BR

        Params:
            url: url of the BR
        Returns: list of KM urls

        """
        def get_hostile_losses(soup):
            """Get tr elements with hostile losses

            Params:
                soup: BeautifulSoup of a BR
            Returns: list of BeautifulSoup(s) of tr elements which contain
                     hostile losses
            """
            main_area = soup.find(id='pilots_and_ships')
            hostile_table = main_area.find_all(class_='kb-table')[-1]
            return hostile_table.find_all('tr', class_='br-destroyed')

        def get_urls(kill, checking_pods):
            """Return url(s) for a given kill on a BR.

            Params:
                kill: a row (BeautifulSoup) where a loss occured
                checking_pods: whether to also return pod loss (if occured)
            Returns: tuple of url(s)

            """
            kill_cells = kill.find_all('td')
            ship_kill_url = kill_cells[0].a.get('href')
            if checking_pods:
                pod_cell = kill_cells[1]
                try:
                    pod_kill_url = pod_cell.find_all('a')[1].get('href')
                except Exception:
                    #pod probably wasn't lost
                    pass
                else:
                    return (ship_kill_url, pod_kill_url)
            return (ship_kill_url,)

        #see if the "Check pods?" checkbox has been ticked
        check_pods = request.form.get('pods', 0) == '1'

        killmail_urls = []
        br = BeautifulSoup(urlopen(url).read())
        for kill in get_hostile_losses(br):
            killmail_urls.extend(get_urls(kill, check_pods))
            logger.info('BR contained KMs: %s', ' and '.join(urls))
        return killmail_urls


def add_scouts(kill_url, scouts, password):
    """Add scouts/logi to a kill

    Params:
        kill_url: url of the KM to be added to
        scouts: list of scouts/logi to be added
        password: password to enable adding of pilots
    Returns:
        A list of error messages

    """
    def checking_present_on_KM():
        """Check if we should check a KM for a pilot before adding"""
        return request.form.get('check', 0) == '1'

    def get_involved_parties(soup):
        """Get involved parties section from a KM"""
        return unicode(soup.find(id='kl-detail-left').table)

    if checking_present_on_KM():
        start_KM = BeautifulSoup(urlopen(kill_url).read())
        check_string = get_involved_parties(start_KM)
    else:
        check_string = ''

    logger.debug('Adding %s to %s', scouts, kill_url)
    errors = []
    for scout in scouts:
        error_msg = ''
        if scout in check_string:
            error_msg = 'Already present'
        else:
            data = urlencode((
                ('scoutname', scout),
                ('password', password),
                ('scoutsubmit', 'add pilot'),
            ))
            try:
                response = urlopen(kill_url, data=data).read()
            except BaseException as e:
                error_msg = 'Error: ' + str(e)
            else:
                if not scout in response:
                    error = re.search('<b>(Error: .+)</b>', response)
                    if error:
                        error_msg = error.groups(1)[0]
                    else:
                        error_msg = 'Unknown error'
        if error_msg:
            error_msg = '{} when adding {} to KM {}'\
                        .format(error_msg, scout, kill_url)
            logger.warning(error_msg)
            errors.append(error_msg)
    return errors


def construct_data(kills, pilots):
    """Construct textarea content for resubmission

    Given a list of kills and a list of pilots, put them together in a
    form that enables them to be fed back into this view

    """
    return '\n'.join(kills + pilots)


def out_of_time(start_time):
    """Check if out of time"""
    return (datetime.now() - start_time).seconds > MAX_RUN_TIME


def create_message(errors, timeout):
    """Create output message
    Params:
        errors: list of errors found (empty if none)
        timeout: boolean of whether request timed out
    Returns: string containing output message
    
    """
    if errors:
        logger.info('\n'.join(errors))
        message = '<br>'.join(errors)
    else:
        logger.info('Successful run')
        message = 'Success!'
    if timeout:
        logger.info('Timed out')
        message += '<br>Ran out of time, please resubmit'
    return message


if __name__ == '__main__':
    app.run(debug=True)
