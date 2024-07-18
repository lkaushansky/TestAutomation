import subprocess
import sys
import os
import glob
import xml.etree.ElementTree as ET
import sqlite3
from tabulate import tabulate
from datetime import datetime


# *********************** START FUNCTIONS ***********************
# function that prints error message to stdout and returns it
def print_return_error(msg):
    print("ERROR: " + msg)
    return msg + "<br>"


def dump_log(rep_file, log_data):
    fh = open(rep_file, "w")
    fh.write(log_data)
    fh.close()


# ***************************** END FUNCTIONS ********************

# load global config
tree = ET.parse('global_test_config.xml')
root = tree.getroot()
qmtExe = root.find('QMT_Editor_location').text
if qmtExe == "" or not os.path.exists(qmtExe):
    print("ERROR: could not locate QMT Editor file at:" + qmtExe)
    exit(1)

# load test cases
testFile = "test_set.xml"
if sys.argv[1] != "" and os.path.exists(sys.argv[1]):
    testfile = sys.argv[1]
else:
    print("ERROR: could not locate test set file:" + sys.argv[1])
    exit(1)
tree = ET.parse(testFile)
root = tree.getroot()
qmtProjDir = root.get('project_dir')
qmtRepPath = qmtProjDir + "\\reports"

# read report header
hdr_file = open("report_header.html", "r")
header = hdr_file.read()
hdr_file.close()

# defile column headers
col_names = ["Test case name", "JIRA Reference", "Result", "Duration", "Verification Details"]
logData: list = []
globStartTime = datetime.now()

# loop through testcases
for testcase in root.findall("testcase"):

    # start logging data
    testStartTime = datetime.now()
    logLineData: list = [testcase.get("name")]
    jiraRef = testcase.find("jiraTestCase")
    if jiraRef is not None:
        logLineData.append(
            '<a href="https://emtgrp2023.atlassian.net/browse/' + jiraRef.text + '">' + jiraRef.text + "</a>")
    else:
        logLineData.append("")

    # get model from  the test case config
    if testcase.find("model") is None:
        logLineData.append('<p style="color:yellow;font-weight:bold">ERROR</p>')
        logLineData.append("--")
        logLineData.append(print_return_error("Could not find model name in the test case configuration for test case "
                                              + testcase.get("name")))
        logData.append(logLineData)
        continue
    model = testcase.find("model").text

    # get the latest DB file for the model
    # qmtDBPath = qmtProjDir + "\\database\\" + model + "_1.db"
    files = glob.glob(qmtProjDir + "\\database\\" + model + "*.db")
    if len(files) == 0:
        print("ERROR: Could not locate db matching the model " + model + " in folder " + qmtProjDir + "\\database")
        logLineData.append('<p style="color:yellow;font-weight:bold">ERROR</p>')
        logLineData.append("--")
        logLineData.append(print_return_error("Could not locate db matching the model " + model + " in folder " +
                                              qmtProjDir + "\\database"))
        logData.append(logLineData)
        continue
    qmtDBPath = max(files, key=os.path.getctime)

    # parse the test database
    dbrows = []
    dbcon = sqlite3.connect(qmtDBPath)
    cur = dbcon.cursor()
    sql = "SELECT tc_id,tc_step,node_type from test_cases order by tc_id,tc_step"
    res = cur.execute(sql)
    for row in res:
        if len(dbrows) < row[0]:
            dbrows.append([])
        dbrows[row[0] - 1].append([row[0], row[1], row[2]])
    dbcon.close()

    # running the command
    cmdLine = qmtExe + " --cli --project-dir " + qmtProjDir + " --db-path " + qmtDBPath
    # ###DEBUG#### print(cmdLine)
    subprocess.run(cmdLine)

    # find latest XML report file for parsing
    files = os.listdir(qmtRepPath)
    paths = [os.path.join(qmtRepPath, basename) for basename in files]
    latestReport = max(paths, key=os.path.getctime)
    # print("Latest report folder is " +latestReport)
    if model not in latestReport:
        logLineData.append('<p style="color:yellow;font-weight:bold">ERROR</p>')
        logLineData.append("--")
        logLineData.append(print_return_error("Could not locate the latest report matching the model name " + model))
        logData.append(logLineData)
        continue
    files = glob.glob(latestReport + "\\*.xml")
    print("Latest report xml file is " + files[0])

    # parse the latest XML report file for test data
    tree = ET.parse(files[0])
    root = tree.getroot()
    testCnt = 0
    stepCnt = 0
    errorCnt = 0
    errorText = ""

    # loop through tests
    for test in root.findall('./suite/test'):
        testCnt += 1
        test_id = int(test.get('id'))
        if test_id != testCnt:
            errorText += print_return_error(
                "test id in the report does not match the sequential test numbering:" + str(test_id))
        print("Verifying test " + str(test_id))

        # get stats
        stats = test.find('stats')
        test_status = stats.get("status")
        if test_status != "PASS":
            errorText += print_return_error("status for Test " + str(test_id) + " is not PASS")
        passed_steps = int(stats.get("pass"))
        if passed_steps != len(dbrows[test_id - 1]):
            errorText += print_return_error("not all steps passed for Test " + str(test_id))
        if test_id != int(dbrows[test_id - 1][0][0]):
            errorText += print_return_error(
                "mismatch between Test id from DB and from XML:" + dbrows[test_id - 1][0][0] + " <> " + test_id)


        # go through steps
        for testStep in test.findall("test_step"):
            stepCnt += 1
            step_id = int(testStep.get('id'))
            # print("\tVerifying step " + str(step_id))
            node_type = testStep.get('node_type')
            step_status = testStep.find("status").get("status")
            # ###DEBUG#### print("Step " + str(step_id) + " Node=" +node_type + " status=" + step_status )
            # ###DEBUG#### print("From DB:" + dbrows[test_id-1][step_id-1][2])
            if step_id != int(dbrows[test_id - 1][step_id - 1][1]):
                errorCnt += 1
                errorText += print_return_error(
                    "mismatch between step id from DB and XML:" + dbrows[test_id - 1][step_id - 1][1] + "<>" + str(
                        step_id))
            if node_type != dbrows[test_id - 1][step_id - 1][2]:
                errorCnt += 1
                errorText += print_return_error("mismatch between node types from DB and XML:" + node_type + "<>" +
                                                dbrows[test_id - 1][step_id - 1][2])
            if step_status != "PASS":
                errorCnt += 1
                errorText += print_return_error("status is not pass for step " + str(step_id))

    # determine if pass or fail
    duration = int((datetime.now()-testStartTime).total_seconds())
    if errorCnt > 0:
        logLineData.append('<p style="color:red;font-weight:bold">FAIL</p>')
        logLineData.append(str(duration) + " sec")
        logLineData.append(errorText)
    else:
        logLineData.append('<p style="color:green;font-weight:bold">PASS</p>')
        logLineData.append(str(duration) + " sec")
        logLineData.append(str(testCnt) + " tests with " + str(stepCnt) + " steps in total passed")
    logData.append(logLineData)

    # dump partial report file in case of failure
    auto_report = header + tabulate(logData, headers=col_names, tablefmt='unsafehtml') + "</body></html>"
    dump_log("c:\\test\\test_report.html", auto_report)

