from copy import deepcopy
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
        print(CONFIG)  # Debug: print config object

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

    if len(number) == 11 and number[:1] == 1:
        number = number[:1]

    return number


def strtobool(s):
    if s.lower() in ['true', '1', 'y', 'yes']:
        return True
    elif s.lower() in ['false', '0', 'n', 'no']:
        return False
    else:
        return None


def format_recruiter(app):
    """Remap application to Recruiter/Web API format.

    Keyword arguments:
    app -- an application dict
    """

    mapped = blank_to_null(app)

    # Define API fields according to required datatypes and/or null handling
    fields_verbatim = ['FirstName',  'LastName',
                       'Email', 'Campus', 'BirthDate', 'CreateDateTime']
    fields_null = ['Prefix', 'MiddleName', 'LastNamePrefix', 'Suffix', 'Nickname', 'GovernmentId', 'LegalName',
                   'Visa', 'CitizenshipStatus', 'PrimaryCitizenship', 'SecondaryCitizenship', 'MaritalStatus',
                   'ProposedDecision', 'Religion', 'FormerLastName', 'FormerFirstName', 'PrimaryLanguage',
                   'CountryOfBirth', 'Disabilities', 'CollegeAttendStatus', 'Commitment', 'Status']
    fields_arr = ['Relationships', 'Activities',
                  'EmergencyContacts', 'Education']
    fields_bool = ['RaceAmericanIndian', 'RaceAsian', 'RaceAfricanAmerican', 'RaceNativeHawaiian',
                   'RaceWhite', 'IsInterestedInCampusHousing', 'IsInterestedInFinancialAid']
    fields_bool = ['RaceAmericanIndian', 'RaceAsian', 'RaceAfricanAmerican', 'RaceNativeHawaiian',
                   'RaceWhite', 'IsInterestedInCampusHousing', 'IsInterestedInFinancialAid']
    fields_int = ['Ethnicity', 'Gender']

    # Pass through some fields verbatim
    mapped.append({k: v for (k, v) in app if k in fields_verbatim})

    # Copy nullable strings from input to output, then fill in nulls
    mapped.append({k: v for (k, v) in app if k in fields_null})
    mapped.append({k: None for k in fields_null if k not in app})

    # Convert integers and booleans
    mapped.update({k: int(v) for (k, v) in app if k in fields_int})
    mapped.update({k: strtobool(v) for (k, v) in app if k in fields_bool})

    # Supply empty arrays. Implementing these would require more logic.
    mapped.append({k: [] for k in fields_arr if k not in app})

    # Probably a stub in the API
    if 'GovernmentDateOfEntry' not in app:
        mapped['GovernmentDateOfEntry'] = '0001-01-01T00:00:00'
    else:
        mapped['GovernmentDateOfEntry'] = app['GovernmentDateOfEntry']

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

    if 'Phone0' in app:
        # Nest up to ten phone numbers as a list of dicts
        mapped['PhoneNumbers'] = [{'Number': format_phone_number(v) for (k, v) in app.items()
                                   if k[:5] == 'Phone' and int(k[5:6]) - 1 == i} for i in range(10)]

        # Supply missing keys
        # Phone numbers will be typed in order from 0-10,
        #   so either order the output from Slate to line up with that or supply Type from Slate
        for k, i in mapped['PhoneNumbers'], range(10):
            if 'Type' not in k:
                k['Type'] = i
            if 'Country' not in k:
                k['Country'] = CONFIG['defaults']['phone_country']

        # Remove empty phone dicts
        mapped['PhoneNumbers'] = [
            k for k in mapped['PhoneNumbers'] if 'Number' in k]
    else:
        # PowerCampus WebAPI requires Type -1 instead of a blank or null when not submitting any phones.
        mapped['PhoneNumbers'] = [
            {'Type': -1, 'Country': None, 'Number': None}]

    # Veteran has funny logic
    if 'Veteran' not in app:
        mapped['Veteran'] = 0
        mapped['VeteranStatus'] = False
    else:
        mapped['Veteran'] = int(mapped['Veteran'])
        mapped['VeteranStatus'] = True

    # Academic program
    mapped['Programs'] = [{'Program': app['Program'],
                           'Degree': app['Degree'], 'Curriculum': None}]

    # GUID's
    mapped['ApplicationNumber'] = app['aid']
    mapped['ProspectId'] = app['pid']

    return mapped


def format_pc(app):
    """Remap application to PowerCampus SQL format.

    Keyword arguments:
    app -- an application dict
    """

    mapped = []

    # Gender is hardcoded into the API. [WebServices].[spSetDemographics] has different hardcoded values.
    gender_map = {None: 3, 0: 1, 1: 2, 2: 3}
    mapped['GENDER'] = gender_map[app['Gender']]

    mapped['ACADEMIC_YEAR'] = RM_MAPPING['AcademicTerm']['PCYearCodeValue'][app['YearTerm']]
    mapped['ACADEMIC_TERM'] = RM_MAPPING['AcademicTerm']['PCTermCodeValue'][app['YearTerm']]
    mapped['ACADEMIC_SESSION'] = '01'
    mapped['PROGRAM'] = RM_MAPPING['AcademicLevel'][app['Programs'][0]['Program']]
    mapped['DEGREE'] = RM_MAPPING['AcademicProgram']['PCDegreeCodeValue'][app['Programs'][0]['Degree']]
    mapped['CURRICULUM'] = RM_MAPPING['AcademicLevel'][app['Programs'][0]['Program']]
    mapped['PRIMARYCITIZENSHIP'] = RM_MAPPING['CitizenshipStatus'][app['CitizenshipStatus']]

    if app['VeteranStatus'] == True:
        mapped['VETERAN'] = RM_MAPPING['Veteran'][str(app['Veteran'])]
    else:
        mapped['VETERAN'] = None

    if app['Visa'] is not None:
        mapped['VISA'] = RM_MAPPING['Visa'][app['Visa']]
    else:
        mapped['VISA'] = None

    if app['SecondaryCitizenship'] is not None:
        mapped['SECONDARYCITIZENSHIP'] = RM_MAPPING['CitizenshipStatus'][app['SecondaryCitizenship']]
    else:
        mapped['SECONDARYCITIZENSHIP'] = None

    if app['MaritalStatus'] is not None:
        mapped['MARITALSTATUS'] = RM_MAPPING['MaritalStatus'][app['MaritalStatus']]
    else:
        mapped['MARITALSTATUS'] = None


def post_to_pc(x):
    """Post an application to PowerCampus.
    Return  PEOPLE_CODE_ID if application was automatically accepted or None for all other conditions.

    Keyword arguments:
    x -- an application dict
    """

    r = requests.post(PC_API_URL + 'api/applications',
                      json=x, auth=PC_API_CRED)
    r.raise_for_status()

    # Catch 202 errors, like ApplicationSettings.config not configured.
    # Not sure if this is the most Pythonic way.
    if r.status_code == 202:
        raise ValueError(r.text)

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
                     x['ApplicationNumber'], auth=PC_API_CRED)
    r.raise_for_status()
    r_dict = json.loads(r.text)

    # If application exists in PowerCampus, execute SP to look for existing PCID.
    # Log PCID and status.
    if 'applicationNumber' in r_dict:
        CURSOR.execute('EXEC [custom].[PS_selRAStatus] \'' +
                       x['ApplicationNumber'] + '\'')
        row = CURSOR.fetchone()
        if row.PEOPLE_CODE_ID is not None:
            PEOPLE_CODE_ID = row.PEOPLE_CODE_ID
            # people_code = row.PEOPLE_CODE_ID[1:]
            # PersonId = row.PersonId # Delete
        else:
            PEOPLE_CODE_ID = None
            people_code = None

        # Determine status.
        if row.ra_status in (0, 3, 4) and row.apl_status == 2 and PEOPLE_CODE_ID is not None:
            computed_status = 'Active'
        elif row.ra_status in (0, 3, 4) and row.apl_status == 3 and PEOPLE_CODE_ID is None:
            computed_status = 'Declined'
        elif row.ra_status in (0, 3, 4) and row.apl_status == 1 and PEOPLE_CODE_ID is None:
            computed_status = 'Pending'
        elif row.ra_status == 1 and row.apl_status is None and PEOPLE_CODE_ID is None:
            computed_status = 'Required field missing.'
        elif row.ra_status == 2 and row.apl_status is None and PEOPLE_CODE_ID is None:
            computed_status = 'Required field mapping is missing.'
        # elif row is not None:
            # ra_status = row.ra_status
        else:
            computed_status = 'Unrecognized Status: ' + str(row.ra_status)

        # Write errors to external database for end-user presentation via SSRS.
        # Append _dev to table name for # Dev v Production
        CURSOR.execute('INSERT INTO' + CONFIG['app_status_log_table'] + """
            ([Ref],[ApplicationNumber],[ProspectId],[FirstName],[LastName],
            [ComputedStatus],[Notes],[RecruiterApplicationStatus],[ApplicationStatus],[PEOPLE_CODE_ID])
        VALUES 
            (?,?,?,?,?,?,?,?,?,?)""",
                       [x['Ref'], x['ApplicationNumber'], x['ProspectId'], x['FirstName'], x['LastName'], computed_status, row.ra_errormessage, row.ra_status, row.apl_status, PEOPLE_CODE_ID])
        CNXN.commit()

        return row.ra_status, row.apl_status, computed_status, PEOPLE_CODE_ID
    else:
        return None, None, None, None


def get_actions(apps_list):
    """Fetch 'Scheduled Actions' (Slate Checklist) for a list of applications.

    Keyword arguments:
    apps_list -- list of ApplicationNumbers to fetch actions for

    Returns:
    app_dict -- list of applications as a dict with nested dicts of actions. Example:
        {'ApplicationNumber': {'ACADEMIC_SESSION': '01',
            'ACADEMIC_TERM': 'SUMMER',
            'ACADEMIC_YEAR': '2019',
            'PEOPLE_CODE_ID': 'P000164949',
            'actions': [{'action_id': 'ADRFLTR',
                'aid': 'ApplicationNumber',
                'completed': 'Y',
                'create_datetime': '2019-01-15T14:17:20',
                'item': 'Gregory Smith, Prinicpal'}]}}

    Uses its own HTTP session to reduce overhead and queries Slate with batches of 48 comma-separated ID's.
    48 was chosen to avoid exceeding max GET request.
    """

    pl = copy.deepcopy(apps_list)
    actions_list = []  # Main list of actions that will be appended to
    # Dict of applications with nested actions that will be returned.
    app_dict = {}

    while pl:
        counter = 0
        ql = []  # Queue list
        qs = ''  # Queue string
        al = []  # Temporary actions list

        # Pop up to 48 ApplicationNumbers and append to queue list.
        while pl and counter < 48:
            ql.append(pl.pop()['ApplicationNumber'])
            counter += 1

        # # Stuff them into a comma-separated string.
        qs = ",".join(str(item) for item in ql)

        r = HTTP_SESSION_SCHED_ACTS.get(
            CONFIG['scheduled_actions']['slate_get']['url'], params={'aids': qs})
        r.raise_for_status()
        al = json.loads(r.text)
        actions_list.extend(al['row'])
        # if len(al['row']) > 1: # Delete. I don't think an application could ever have zero actions.

    # Rebuild the list of applications with the actions nested
    for k, v in enumerate(apps_list):
        app_dict.update({apps_list[k]['ApplicationNumber']: {'PEOPLE_CODE_ID': apps_list[k]['PEOPLE_CODE_ID'],
                                                             'ACADEMIC_YEAR': apps_list[k]['ACADEMIC_YEAR'],
                                                             'ACADEMIC_TERM': apps_list[k]['ACADEMIC_TERM'],
                                                             'ACADEMIC_SESSION': apps_list[k]['ACADEMIC_SESSION'],
                                                             'actions': []}})

    for k, v in enumerate(actions_list):
        app_dict[actions_list[k]['aid']]['actions'].append(actions_list[k])

    return app_dict


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
                   app['PEOPLE_CODE_ID'], app['year'], app['term'], app['session'], app['program'], app['degree'], app['curriculum'])
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


def pc_update_actions(app):
    for k, v in enumerate(app['actions']):
        CURSOR.execute('EXEC [custom].[PS_updAction] ?, ?, ?, ?, ?, ?, ?, ?, ?',
                       app['PEOPLE_CODE_ID'],
                       'SLATE',
                       k['action_id'],
                       k['item'],
                       k['completed'],
                       # Only the date portion is actually used.
                       k['create_datetime'],
                       app['ACADEMIC_YEAR'],
                       app['ACADEMIC_TERM'],
                       app['ACADEMIC_SESSION'])
        CNXN.commit()


def pc_update_smsoptin(app):
    if 'SMSOptIn' in app:
        CURSOR.execute('exec [custom].[PS_updSMSOptIn] ?, ?, ?',
                       app['PEOPLE_CODE_ID'], 'SLATE', app['SMSOptIn'])
        CNXN.commit()


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
    if len(apps) == 0:
        raise EOFError(ERROR_STRINGS['no_apps'])

    # Check each app's status flags/PCID in PowerCampus and store them
    for k, v in apps.items():
        status_ra, status_app, status_calc, PEOPLE_CODE_ID = scan_status(v)
        v.update({'status_ra': status_ra, 'status_app': status_app,
                  'status_calc': status_calc})
        v['PEOPLE_CODE_ID'] = PEOPLE_CODE_ID

    # (Re)Post new or unprocessed applications to PowerCampus API
    for k, v in apps.items():
        if (v['status_ra'] == None) or (v['status_ra'] in (1, 2) and v['status_app'] is None):
            PEOPLE_CODE_ID = post_to_pc(v)
            v['PEOPLE_CODE_ID'] = PEOPLE_CODE_ID

    # Rescan statuses
    for k, v in apps.items():
        status_ra, status_app, status_calc, PEOPLE_CODE_ID = scan_status(v)
        v.update({'status_ra': status_ra, 'status_app': status_app,
                  'status_calc': status_calc})
        v['PEOPLE_CODE_ID'] = PEOPLE_CODE_ID

    # Update existing applications in PowerCampus and extract information
    for k, v in apps.items():
        if v['status_calc'] == 'Active':
            # Transform to PowerCampus format
            app_pc = format_pc(v)

            # Execute update sprocs
            pc_update_demographics(app_pc)
            pc_update_statusdecision(app_pc)
            pc_update_statusdecision(app_pc)

            # Collect information
            found, registered, reg_date, readmit, withdrawn, credits, campus_email = pc_get_profile(
                v)
            v.update({'found': found, 'registered': registered, 'reg_date': reg_date, 'readmit': readmit,
                      'withdrawn': withdrawn, 'credits': credits, 'campus_email': campus_email})

    # Update PowerCampus Scheduled Actions
    if CONFIG['scheduled_actions']['enabled'] == True:
        apps_for_sa = [k for (k, v) in apps.items()
                       if apps['status_calc'] == 'Active']
        actions = get_actions(apps_for_sa)

        for k, v in actions.items():
            pc_update_actions(v)

    # Upload data back to Slate
    # Build list of flat app dicts with only certain fields included
    slate_upload_list = []
    slate_upload_fields = ['aid', 'PEOPLE_CODE_ID', 'found', 'registered',
                           'reg_date', 'readmit', 'withdrawn', 'credits', 'campus_email']
    for k, v in apps.items():
        slate_upload_list.append(
            {k: v for (k, v) in v.items() if k in slate_upload_fields})

    # Slate requires JSON to be convertable to XML
    slate_upload_dict = {'row': slate_upload_list}

    creds = (CONFIG['slate_upload']['username'],
             CONFIG['slate_upload']['password'])
    r = requests.post(CONFIG['slate_upload']['url'],
                      json=slate_upload_dict, auth=creds)
    r.raise_for_status()

    return 'Done. Please check the PowerSlate Sync Report for more details.'
