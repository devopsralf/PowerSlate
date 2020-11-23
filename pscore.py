from copy import deepcopy, error
from sys import hash_info
from typing import Mapping
import requests
import copy
import json
import xml.etree.ElementTree as ET
import pyodbc
import datetime
from string import ascii_letters, punctuation, whitespace


def init_config(config_path):
    """Reads config file to global 'config' dict. Many frequently-used variables are copied to their own globals for convenince.

    Returns SMTP config dict for crash handling."""
    global CONFIG
    global PC_API_URL
    global PC_API_CRED
    global HTTP_SESSION_SCHED_ACTS
    global RM_MAPPING
    global CNXN
    global CURSOR
    global TODAY
    global ERROR_STRINGS

    # Read config file and convert to dict
    with open(config_path) as config_path:
        CONFIG = json.loads(config_path.read())

    # We will use recruiterMapping.xml to translate Recruiter values to PowerCampus values for direct SQL operations.
    # The file path can be local or remote. Obviously, a remote file must have proper network share and permissions set up.
    # Remote is more convenient, as local requires you to manually copy the file whenever you change it with the
    # PowerCampus Mapping Tool. Note: The tool produces UTF-8 BOM encoded files, so I explicity specify utf-8-sig.

    # Parse XML mapping file into dict rm_mapping
    with open(CONFIG['mapping_file_location'], encoding='utf-8-sig') as treeFile:
        tree = ET.parse(treeFile)
        doc = tree.getroot()
    RM_MAPPING = {}

    for child in doc:
        if child.get('NumberOfPowerCampusFieldsMapped') == '1':
            RM_MAPPING[child.tag] = {}
            for row in child:
                RM_MAPPING[child.tag].update(
                    {row.get('RCCodeValue'): row.get('PCCodeValue')})

        if child.get('NumberOfPowerCampusFieldsMapped') == '2' or child.get('NumberOfPowerCampusFieldsMapped') == '3':
            fn1 = 'PC' + str(child.get('PCFirstField')) + 'CodeValue'
            fn2 = 'PC' + str(child.get('PCSecondField')) + 'CodeValue'
            RM_MAPPING[child.tag] = {fn1: {}, fn2: {}}

            for row in child:
                RM_MAPPING[child.tag][fn1].update(
                    {row.get('RCCodeValue'): row.get(fn1)})
                RM_MAPPING[child.tag][fn2].update(
                    {row.get('RCCodeValue'): row.get(fn2)})

    # PowerCampus Web API connection
    PC_API_URL = CONFIG['pc_api']['url']
    PC_API_CRED = (CONFIG['pc_api']['username'], CONFIG['pc_api']['password'])

    # Set up an HTTP session to be used for updating scheduled actions. It's initialized here because it will be used
    # inside a loop. Other web service calls will use the top-level requests functions (i.e. their own, automatic sessions).
    if CONFIG['scheduled_actions']['enabled'] == True:
        HTTP_SESSION_SCHED_ACTS = requests.Session()
        HTTP_SESSION_SCHED_ACTS.auth = (
            CONFIG['scheduled_actions']['slate_get']['username'], CONFIG['scheduled_actions']['slate_get']['password'])

    # Microsoft SQL Server connection.
    CNXN = pyodbc.connect(CONFIG['pc_database_string'])
    CURSOR = CNXN.cursor()

    today = datetime.datetime.date(datetime.datetime.now())

    # Config dicts
    smtp_config = CONFIG['smtp']
    ERROR_STRINGS = CONFIG['error_strings']

    # Print a test of connections
    r = requests.get(PC_API_URL + 'api/version', auth=PC_API_CRED)
    print('PowerCampus API Status: ' + str(r.status_code))
    print(r.text)
    r.raise_for_status()
    print(CNXN.getinfo(pyodbc.SQL_DATABASE_NAME))

    return smtp_config


def de_init():
    # Clean up connections.
    CNXN.close()  # SQL

    if CONFIG['scheduled_actions']['enabled'] == True:
        HTTP_SESSION_SCHED_ACTS.close()  # HTTP session to Slate for scheduled actions


def blank_to_null(x):
    # Converts empty string to None. Accepts dicts, lists, and tuples.
    # This function derived from radtek @ http://stackoverflow.com/a/37079737/4109658
    # CC Attribution-ShareAlike 3.0 https://creativecommons.org/licenses/by-sa/3.0/
    ret = copy.deepcopy(x)
    # Handle dictionaries, lists, and tuples. Scrub all values
    if isinstance(x, dict):
        for k, v in ret.items():
            ret[k] = blank_to_null(v)
    if isinstance(x, (list, tuple)):
        for k, v in enumerate(ret):
            ret[k] = blank_to_null(v)
    # Handle None
    if x == '':
        ret = None
    # Finished scrubbing
    return ret


def format_phone_number(number):
    """Strips anything but digits from a phone number and removes US country code."""
    non_digits = str.maketrans(
        {c: None for c in ascii_letters + punctuation + whitespace})
    number = number.translate(non_digits)

    if len(number) == 11 and number[:1] == '1':
        number = number[1:]

    return number


def strtobool(s):
    if s.lower() in ['true', '1', 'y', 'yes']:
        return True
    elif s.lower() in ['false', '0', 'n', 'no']:
        return False
    else:
        return None


def format_app_generic(app):
    """Supply missing fields and correct datatypes. Returns a flat dict."""

    mapped = blank_to_null(app)

    fields_null = ['Prefix', 'MiddleName', 'LastNamePrefix', 'Suffix', 'Nickname', 'GovernmentId', 'LegalName',
                   'Visa', 'CitizenshipStatus', 'PrimaryCitizenship', 'SecondaryCitizenship', 'MaritalStatus',
                   'ProposedDecision', 'Religion', 'FormerLastName', 'FormerFirstName', 'PrimaryLanguage',
                   'CountryOfBirth', 'Disabilities', 'CollegeAttendStatus', 'Commitment', 'Status', 'Veteran']
    fields_bool = ['RaceAmericanIndian', 'RaceAsian', 'RaceAfricanAmerican', 'RaceNativeHawaiian',
                   'RaceWhite', 'IsInterestedInCampusHousing', 'IsInterestedInFinancialAid']
    fields_bool = ['RaceAmericanIndian', 'RaceAsian', 'RaceAfricanAmerican', 'RaceNativeHawaiian',
                   'RaceWhite', 'IsInterestedInCampusHousing', 'IsInterestedInFinancialAid']
    fields_int = ['Ethnicity', 'Gender', 'SMSOptIn']

    # Copy nullable strings from input to output, then fill in nulls
    mapped.update({k: v for (k, v) in app.items() if k in fields_null})
    mapped.update({k: None for k in fields_null if k not in app})

    # Convert integers and booleans
    mapped.update({k: int(v) for (k, v) in app.items() if k in fields_int})
    mapped.update({k: strtobool(v)
                   for (k, v) in app.items() if k in fields_bool})

    # Probably a stub in the API
    if 'GovernmentDateOfEntry' not in app:
        mapped['GovernmentDateOfEntry'] = '0001-01-01T00:00:00'
    else:
        mapped['GovernmentDateOfEntry'] = app['GovernmentDateOfEntry']

    # Pass through all other fields
    mapped.update({k: v for (k, v) in app.items() if k not in mapped})

    return mapped


def format_app_api(app):
    """Remap application to Recruiter/Web API format.

    Keyword arguments:
    app -- an application dict
    """

    mapped = {}

    # Pass through fields
    fields_verbatim = ['FirstName',  'LastName', 'Email', 'Campus', 'BirthDate', 'CreateDateTime',
                       'Prefix', 'MiddleName', 'LastNamePrefix', 'Suffix', 'Nickname', 'GovernmentId', 'LegalName',
                       'Visa', 'CitizenshipStatus', 'PrimaryCitizenship', 'SecondaryCitizenship', 'MaritalStatus',
                       'ProposedDecision', 'Religion', 'FormerLastName', 'FormerFirstName', 'PrimaryLanguage',
                       'CountryOfBirth', 'Disabilities', 'CollegeAttendStatus', 'Commitment', 'Status',
                       'RaceAmericanIndian', 'RaceAsian', 'RaceAfricanAmerican', 'RaceNativeHawaiian',
                       'RaceWhite', 'IsInterestedInCampusHousing', 'IsInterestedInFinancialAid'
                       'Ethnicity', 'Gender', 'YearTerm']
    mapped.update({k: v for (k, v) in app.items() if k in fields_verbatim})

    # Supply empty arrays. Implementing these would require more logic.
    fields_arr = ['Relationships', 'Activities',
                  'EmergencyContacts', 'Education']
    mapped.update({k: [] for k in fields_arr if k not in app})

    # Nest up to ten addresses as a list of dicts
    # "Address1Line1": "123 St" becomes "Addresses": [{"Line1": "123 St"}]
    mapped['Addresses'] = [{k[8:]: v for (k, v) in app.items()
                            if k[0:7] == 'Address' and int(k[7:8]) - 1 == i} for i in range(10)]

    # Remove empty address dicts
    mapped['Addresses'] = [k for k in mapped['Addresses'] if len(k) > 0]

    # Supply missing keys
    for k in mapped['Addresses']:
        if 'Type' not in k:
            k['Type'] = 0
        # If any of  Line1-4 are missing, insert them with value = None
        k.update({'Line' + str(i+1): None for i in range(4)
                  if 'Line' + str(i+1) not in k})
        if 'City' not in k:
            k['City'] = None
        if 'StateProvince' not in k:
            k['StateProvince'] = None
        if 'PostalCode' not in k:
            k['PostalCode'] = None
        if 'County' not in k:
            k['County'] = CONFIG['defaults']['address_country']

    if len([k for k in app if k[:5] == 'Phone']) > 0:
        has_phones = True
    else:
        has_phones = False

    if has_phones == True:
        # Nest up to 9 phone numbers as a list of dicts.
        # Phones should be passed in as {Phone0Number: '...', Phone0Type: 1, Phone1Number: '...', Phone1Country: '...', Phone1Type: 0}
        # First phone in the list becomes Primary in PowerCampus (I think)
        mapped['PhoneNumbers'] = [{k[6:]: v for (k, v) in app.items(
        ) if k[:5] == 'Phone' and int(k[5:6]) - 1 == i} for i in range(9)]

        # Remove empty dicts
        mapped['PhoneNumbers'] = [
            k for k in mapped['PhoneNumbers'] if 'Number' in k]

        # Supply missing keys and enforce datatypes
        for i, item in enumerate(mapped['PhoneNumbers']):
            item['Number'] = format_phone_number(item['Number'])

            if 'Type' not in item:
                item['Type'] = CONFIG['defaults']['phone_type']
            else:
                item['Type'] = int(item['Type'])

            if 'Country' not in item:
                item['Country'] = CONFIG['defaults']['phone_country']

    else:
        # PowerCampus WebAPI requires Type -1 instead of a blank or null when not submitting any phones.
        mapped['PhoneNumbers'] = [
            {'Type': -1, 'Country': None, 'Number': None}]

    # Veteran has funny logic
    if app['Veteran'] is None:
        mapped['Veteran'] = 0
        mapped['VeteranStatus'] = False
    else:
        mapped['Veteran'] = int(app['Veteran'])
        mapped['VeteranStatus'] = True

    # Academic program
    mapped['Programs'] = [{'Program': app['Program'],
                           'Degree': app['Degree'], 'Curriculum': None}]

    # GUID's
    mapped['ApplicationNumber'] = app['aid']
    mapped['ProspectId'] = app['pid']

    return mapped


def format_app_sql(app):
    """Remap application to PowerCampus SQL format.

    Keyword arguments:
    app -- an application dict
    """

    mapped = {}

    # Pass through fields
    fields_verbatim = ['PEOPLE_CODE_ID', 'RaceAmericanIndian', 'RaceAsian', 'RaceAfricanAmerican', 'RaceNativeHawaiian',
                       'RaceWhite', 'IsInterestedInCampusHousing', 'IsInterestedInFinancialAid', 'RaceWhite', 'Ethnicity',
                       'ProposedDecision', 'CreateDateTime', 'SMSOptIn']
    mapped.update({k: v for (k, v) in app.items() if k in fields_verbatim})

    # Gender is hardcoded into the PowerCampus Web API, but [WebServices].[spSetDemographics] has different hardcoded values.
    gender_map = {None: 3, 0: 1, 1: 2, 2: 3}
    mapped['GENDER'] = gender_map[app['Gender']]

    mapped['ACADEMIC_YEAR'] = RM_MAPPING['AcademicTerm']['PCYearCodeValue'][app['YearTerm']]
    mapped['ACADEMIC_TERM'] = RM_MAPPING['AcademicTerm']['PCTermCodeValue'][app['YearTerm']]
    mapped['ACADEMIC_SESSION'] = '01'
    # Todo: Fix inconsistency of 1-field vs 2-field mappings
    mapped['PROGRAM'] = RM_MAPPING['AcademicLevel'][app['Program']]
    mapped['DEGREE'] = RM_MAPPING['AcademicProgram']['PCDegreeCodeValue'][app['Degree']]
    mapped['CURRICULUM'] = RM_MAPPING['AcademicProgram']['PCCurriculumCodeValue'][app['Degree']]
    mapped['PRIMARYCITIZENSHIP'] = RM_MAPPING['CitizenshipStatus'][app['CitizenshipStatus']]

    if app['Visa'] is not None:
        mapped['VISA'] = RM_MAPPING['Visa'][app['Visa']]
    else:
        mapped['VISA'] = None

    if 'VeteranStatus' in app and app['VeteranStatus'] == True:
        mapped['VETERAN'] = RM_MAPPING['Veteran'][str(app['Veteran'])]
    else:
        mapped['VETERAN'] = None

    if app['SecondaryCitizenship'] is not None:
        mapped['SECONDARYCITIZENSHIP'] = RM_MAPPING['CitizenshipStatus'][app['SecondaryCitizenship']]
    else:
        mapped['SECONDARYCITIZENSHIP'] = None

    if app['MaritalStatus'] is not None:
        mapped['MARITALSTATUS'] = RM_MAPPING['MaritalStatus'][app['MaritalStatus']]
    else:
        mapped['MARITALSTATUS'] = None

    return mapped


def pc_post_api(x):
    """Post an application to PowerCampus.
    Return  PEOPLE_CODE_ID if application was automatically accepted or None for all other conditions.

    Keyword arguments:
    x -- an application dict
    """

    r = requests.post(PC_API_URL + 'api/applications',
                      json=x, auth=PC_API_CRED)

    # Catch some errors we know how to handle. Not sure if this is the most Pythonic way.
    # 202 probably means ApplicationSettings.config not configured.
    if r.status_code == 202:
        raise ValueError(r.text)
    elif r.status_code == 400:
        raise ValueError(r.text)

    r.raise_for_status()

    if (r.text[-25:-12] == 'New People Id'):
        try:
            people_code = r.text[-11:-2]
            # Error check. After slice because leading zeros need preserved.
            int(people_code)
            PEOPLE_CODE_ID = 'P' + people_code
            return PEOPLE_CODE_ID
        except:
            return None
    else:
        return None


def str_digits(s):
    # Returns only digits from a string.
    non_digits = str.maketrans(
        {c: None for c in ascii_letters + punctuation + whitespace})
    return s.translate(non_digits)


def scan_status(x):
    # Scan the PowerCampus status of a single applicant and return it in three parts plus three ID numbers.
    # Expects a dict

    r = requests.get(PC_API_URL + 'api/applications?applicationNumber=' +
                     x['aid'], auth=PC_API_CRED)
    r.raise_for_status()
    r_dict = json.loads(r.text)

    # If application exists in PowerCampus, execute SP to look for existing PCID.
    # Log PCID and status.
    if 'applicationNumber' in r_dict:
        CURSOR.execute('EXEC [custom].[PS_selRAStatus] \'' +
                       x['aid'] + '\'')
        row = CURSOR.fetchone()
        if row.PEOPLE_CODE_ID is not None:
            pcid = row.PEOPLE_CODE_ID
            # people_code = row.PEOPLE_CODE_ID[1:]
            # PersonId = row.PersonId # Delete
        else:
            pcid = None
            people_code = None

        # Determine status.
        if row.ra_status in (0, 3, 4) and row.apl_status == 2 and pcid is not None:
            computed_status = 'Active'
        elif row.ra_status in (0, 3, 4) and row.apl_status == 3 and pcid is None:
            computed_status = 'Declined'
        elif row.ra_status in (0, 3, 4) and row.apl_status == 1 and pcid is None:
            computed_status = 'Pending'
        elif row.ra_status == 1 and row.apl_status is None and pcid is None:
            computed_status = 'Required field missing.'
        elif row.ra_status == 2 and row.apl_status is None and pcid is None:
            computed_status = 'Required field mapping is missing.'
        # elif row is not None:
            # ra_status = row.ra_status
        else:
            computed_status = 'Unrecognized Status: ' + str(row.ra_status)

        # Write errors to external database for end-user presentation via SSRS.
        CURSOR.execute('INSERT INTO' + CONFIG['app_status_log_table'] + """
            ([Ref],[ApplicationNumber],[ProspectId],[FirstName],[LastName],
            [ComputedStatus],[Notes],[RecruiterApplicationStatus],[ApplicationStatus],[PEOPLE_CODE_ID])
        VALUES
            (?,?,?,?,?,?,?,?,?,?)""",
                       [x['Ref'], x['aid'], x['pid'], x['FirstName'], x['LastName'], computed_status, row.ra_errormessage, row.ra_status, row.apl_status, pcid])
        CNXN.commit()

        return row.ra_status, row.apl_status, computed_status, pcid
    else:
        return None, None, None, None


def slate_get_actions(apps_list):
    """Fetch 'Scheduled Actions' (Slate Checklist) for a list of applications.

    Keyword arguments:
    apps_list -- list of ApplicationNumbers to fetch actions for

    Returns:
    action_list -- list of individual action as dicts

    Uses its own HTTP session to reduce overhead and queries Slate with batches of 48 comma-separated ID's.
    48 was chosen to avoid exceeding max GET request.
    """

    actions_list = []

    while apps_list:
        counter = 0
        ql = []  # Queue list
        qs = ''  # Queue string
        al = []  # Temporary actions list

        # Pop up to 48 app GUID's and append to queue list.
        while apps_list and counter < 48:
            ql.append(apps_list.pop())
            counter += 1

        # Stuff them into a comma-separated string.
        qs = ",".join(str(item) for item in ql)

        r = HTTP_SESSION_SCHED_ACTS.get(
            CONFIG['scheduled_actions']['slate_get']['url'], params={'aids': qs})
        r.raise_for_status()
        al = json.loads(r.text)
        actions_list.extend(al['row'])
        # if len(al['row']) > 1: # Delete. I don't think an application could ever have zero actions.

    return actions_list


def pc_get_profile(app):
    '''Fetch ACADEMIC row data and email address from PowerCampus.

     Returns:
     found -- True/False (row exists or not)
     registered -- True/False
     reg_date -- Date
     readmit -- True/False
     withdrawn -- True/False
     credits -- string
     campus_email -- string (None of not registered)
    '''

    found = False
    registered = False
    reg_date = None
    readmit = False
    withdrawn = False
    credits = 0
    campus_email = None

    CURSOR.execute('EXEC [custom].[PS_selProfile] ?,?,?,?,?,?,?',
                   app['PEOPLE_CODE_ID'],
                   app['ACADEMIC_YEAR'],
                   app['ACADEMIC_TERM'],
                   app['ACADEMIC_SESSION'],
                   app['PROGRAM'],
                   app['DEGREE'],
                   app['CURRICULUM'])
    row = CURSOR.fetchone()

    if row is not None:
        found = True

        if row.Registered == 'Y':
            registered = True
            reg_date = str(row.REG_VAL_DATE)
            credits = str(row.CREDITS)
            campus_email = row.CampusEmail

        if row.COLLEGE_ATTEND == 'READ':
            readmit = True

        if row.Withdrawn == 'Y':
            withdrawn = True

    return found, registered, reg_date, readmit, withdrawn, credits, campus_email


def pc_update_demographics(app):
    CURSOR.execute('execute [custom].[PS_updDemographics] ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?',
                   app['PEOPLE_CODE_ID'],
                   'SLATE',
                   app['GENDER'],
                   app['Ethnicity'],
                   app['MARITALSTATUS'],
                   app['VETERAN'],
                   app['PRIMARYCITIZENSHIP'],
                   app['SECONDARYCITIZENSHIP'],
                   app['VISA'],
                   app['RaceAfricanAmerican'],
                   app['RaceAmericanIndian'],
                   app['RaceAsian'],
                   app['RaceNativeHawaiian'],
                   app['RaceWhite'])
    CNXN.commit()


def pc_update_statusdecision(app):
    CURSOR.execute('exec [custom].[PS_updAcademicAppInfo] ?, ?, ?, ?, ?, ?, ?, ?, ?',
                   app['PEOPLE_CODE_ID'],
                   app['ACADEMIC_YEAR'],
                   app['ACADEMIC_TERM'],
                   app['ACADEMIC_SESSION'],
                   app['PROGRAM'],
                   app['DEGREE'],
                   app['CURRICULUM'],
                   app['ProposedDecision'],
                   app['CreateDateTime'])
    CNXN.commit()


def pc_update_action(action):
    """Update a Scheduled Action in PowerCampus. Expects an action dict with 'app' key containing SQL formatted app
    {'aid': GUID, 'item': 'Transcript', 'app': {'PEOPLE_CODE_ID':...}}
    """
    try:
        CURSOR.execute('EXEC [custom].[PS_updAction] ?, ?, ?, ?, ?, ?, ?, ?, ?',
                       action['app']['PEOPLE_CODE_ID'],
                       'SLATE',
                       action['action_id'],
                       action['item'],
                       action['completed'],
                       # Only the date portion is actually used.
                       action['create_datetime'],
                       action['app']['ACADEMIC_YEAR'],
                       action['app']['ACADEMIC_TERM'],
                       action['app']['ACADEMIC_SESSION'])
        CNXN.commit()
    except KeyError as e:
        raise KeyError(e, 'aid: ' + action['aid'])


def pc_update_smsoptin(app):
    if 'SMSOptIn' in app:
        CURSOR.execute('exec [custom].[PS_updSMSOptIn] ?, ?, ?',
                       app['PEOPLE_CODE_ID'], 'SLATE', app['SMSOptIn'])
        CNXN.commit()


def pf_get_fachecklist(pcid, govid, appid, year, term, session):
    """Return the PowerFAIDS missing docs list for uploading to Financial Aid Checklist."""
    checklist = []
    CURSOR.execute(
        'exec [custom].[PS_selPFChecklist] ?, ?, ?, ?, ?', pcid, govid, year, term, session)

    columns = [column[0] for column in CURSOR.description]
    for row in CURSOR.fetchall():
        checklist.append(dict(zip(columns, row)))

    # Pass through the Slate Application ID
    for doc in checklist:
        doc['AppID'] = appid

    return checklist


def main_sync(pid=None):
    """Main body of the program.

    Keyword arguments:
    pid -- specific application GUID to sync (default None)
    """

    # Get applicants from Slate
    creds = (CONFIG['slate_query_apps']['username'],
             CONFIG['slate_query_apps']['password'])
    if pid is not None:
        r = requests.get(CONFIG['slate_query_apps']['url'],
                         auth=creds, params={'pid': pid})
    else:
        r = requests.get(CONFIG['slate_query_apps']['url'], auth=creds)
    r.raise_for_status()
    apps = json.loads(r.text)['row']

    # Make a dict of apps with application GUID as the key
    # {AppGUID: { JSON from Slate }
    apps = {k['aid']: k for k in apps}
    if len(apps) == 0 and pid is not None:
        # Assuming we're running in interactive (HTTP) mode if pid param exists
        raise EOFError(ERROR_STRINGS['no_apps'])
    elif len(apps) == 0:
        # Don't raise an error for scheduled mode
        return None

    # Clean up app data from Slate (datatypes, supply nulls, etc.)
    for k, v in apps.items():
        apps[k] = format_app_generic(v)

    # Check each app's status flags/PCID in PowerCampus and store them
    for k, v in apps.items():
        status_ra, status_app, status_calc, pcid = scan_status(v)
        apps[k].update({'status_ra': status_ra, 'status_app': status_app,
                        'status_calc': status_calc})
        apps[k]['PEOPLE_CODE_ID'] = pcid

    # (Re)Post new or unprocessed applications to PowerCampus API
    for k, v in apps.items():
        if (v['status_ra'] == None) or (v['status_ra'] in (1, 2) and v['status_app'] is None):
            pcid = pc_post_api(format_app_api(v))
            apps[k]['PEOPLE_CODE_ID'] = pcid

    # Rescan statuses
    for k, v in apps.items():
        status_ra, status_app, status_calc, pcid = scan_status(v)
        apps[k].update({'status_ra': status_ra, 'status_app': status_app,
                        'status_calc': status_calc})
        apps[k]['PEOPLE_CODE_ID'] = pcid

    # Update existing applications in PowerCampus and extract information
    for k, v in apps.items():
        if v['status_calc'] == 'Active':
            # Transform to PowerCampus format
            app_pc = format_app_sql(v)

            # Execute update sprocs
            pc_update_demographics(app_pc)
            pc_update_statusdecision(app_pc)
            pc_update_statusdecision(app_pc)
            pc_update_smsoptin(app_pc)

            # Collect information
            found, registered, reg_date, readmit, withdrawn, credits, campus_email = pc_get_profile(
                app_pc)
            apps[k].update({'found': found, 'registered': registered, 'reg_date': reg_date, 'readmit': readmit,
                            'withdrawn': withdrawn, 'credits': credits, 'campus_email': campus_email})

    # Update PowerCampus Scheduled Actions
    # Querying each app individually would introduce significant network overhead, so query Slate in bulk
    if CONFIG['scheduled_actions']['enabled'] == True:
        # Make a list of App GUID's
        apps_for_sa = [k for (k, v) in apps.items()
                       if v['status_calc'] == 'Active']
        actions_list = slate_get_actions(apps_for_sa)

        for action in actions_list:
            # Lookup the app each action is associated with; we need PCID and YTS
            # Nest SQL version of app underneath action
            action['app'] = format_app_sql(apps[action['aid']])
            pc_update_action(action)

    # Upload data back to Slate
    # Build list of flat app dicts with only certain fields included
    slate_upload_list = []
    slate_upload_fields = ['aid', 'PEOPLE_CODE_ID', 'found', 'registered',
                           'reg_date', 'readmit', 'withdrawn', 'credits', 'campus_email']
    for app in apps.values():
        slate_upload_list.append(
            {k: v for (k, v) in app.items() if k in slate_upload_fields})

    # Slate requires JSON to be convertable to XML
    slate_upload_dict = {'row': slate_upload_list}

    creds = (CONFIG['slate_upload']['username'],
             CONFIG['slate_upload']['password'])
    r = requests.post(CONFIG['slate_upload']['url'],
                      json=slate_upload_dict, auth=creds)
    r.raise_for_status()

    # Collect Financial Aid checklist and upload to Slate
    if CONFIG['fa_checklist']['enabled'] == True:
        slate_upload_list = []
        slate_upload_fields = {'AppID', 'Code', 'Status', 'Date'}

        for k, v in apps.items():
            if v['status_calc'] == 'Active':
                # Transform to PowerCampus format
                app_pc = format_app_sql(v)

                fa_checklists = pf_get_fachecklist(
                    app_pc['PEOPLE_CODE_ID'], v['GovernmentId'], v['AppID'], app_pc['ACADEMIC_YEAR'], app_pc['ACADEMIC_TERM'], app_pc['ACADEMIC_SESSION'])

                slate_upload_list = slate_upload_list + fa_checklists

        if len(slate_upload_list) > 0:
            # Slate's Checklist Import (Financial Aid) requires tab-separated files because it's old and crusty, apparently.
            tab = '\t'
            slate_fa_string = 'AppID' + tab + 'Code' + tab + 'Status' + tab + 'Date'
            for i in slate_upload_list:
                line = i['AppID'] + tab + \
                    str(i['Code']) + tab + i['Status'] + tab + i['Date']
                slate_fa_string = slate_fa_string + '\n' + line

            creds = (CONFIG['fa_checklist']['slate_post']['username'],
                     CONFIG['fa_checklist']['slate_post']['password'])
            r = requests.post(CONFIG['fa_checklist']['slate_post']['url'],
                              data=slate_fa_string, auth=creds)
            r.raise_for_status()

    return 'Done. Please check the PowerSlate Sync Report for more details.'
