import subprocess
import sys
import os
import glob
import xml.etree.ElementTree as ET
import sqlite3
from tabulate import tabulate

# function that prints error message to stdout and returns it
def print_return_error(msg):
    print("ERROR: " + msg)
    return msg + "<br>"

# load global config
tree = ET.parse('global_test_config.xml')
root = tree.getroot()
qmtExe = root.find('QMT_Editor_location').text

## load test cases
tree = ET.parse(sys.argv[1])
root = tree.getroot()
qmtProjDir = root.get('project_dir')
qmtRepPath = qmtProjDir + "\\reports"

logData: list = []

# loop through testcases
for testcase in root.findall("testcase"):

    # start logging data
    logLineData: list = [testcase.get("name")]
    jiraRef = testcase.find("jiratestcase")
    if jiraRef is not None:
        logLineData.append(
            '<a href="https://emtgrp2023.atlassian.net/browse/' + jiraRef.text + '">' + jiraRef.text + "</a>")
    else:
        logLineData.append("")

    # get model from  the test case config
    if testcase.find("model") is None:
        logLineData.append("ERROR")
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
        logLineData.append("ERROR")
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
            dbrows.append([]);
        dbrows[row[0] - 1].append([row[0], row[1], row[2]])
    dbcon.close()

    # running the command
    cmdLine = qmtExe + " --cli --project-dir " + qmtProjDir + " --db-path " + qmtDBPath
    # ###DEBUG#### print(cmdLine)
    # subprocess.run(cmdLine)

    # find latest XML report file for parsing
    files = os.listdir(qmtRepPath)
    paths = [os.path.join(qmtRepPath, basename) for basename in files]
    latestReport = max(paths, key=os.path.getctime)
    # print("Latest report folder is " +latestReport)
    if model not in latestReport:
        logLineData.append("ERROR")
        logLineData.append(print_return_error("Could not locate the latest report matching the model name " + model))
        logData.append(logLineData)
        continue
    files = glob.glob(latestReport + "\\*.xml")
    print("Latest report xml file is " + files[0])

    # parse the latest XML report file for test data
    tree = ET.parse(files[0])
    root = tree.getroot()
    testCnt = 0
    errorCnt = 0
    errorText = ""

    # loop through tests
    for test in root.findall('./suite/test'):
        testCnt += 1
        test_id = int(test.get('id'))
        if test_id != testCnt:
            errorText += print_return_error("test id in the report does not match the sequential test numbering:" + str(test_id))
        print("Verifying test " + str(test_id))

        # get stats
        stats = test.find('stats')
        test_status = stats.get("status")
        if test_status != "PASS":
            errorText += print_return_error("status for Test " + str(test_id) + " is not PASS")
        passed_steps = int(stats.get("pass"))
        if passed_steps != len(dbrows[test_id-1]):
            errorText += print_return_error("not all steps passed for Test " + str(test_id))
        if test_id != int(dbrows[test_id-1][0][0]):
            errorText += print_return_error(
                "mismatch between Test id from DB and from XML:"+dbrows[test_id-1][0][0]+" <> "+test_id)
        ####DEBUG#### print("Test status is " + test_status)
        ####DEBUG#### print("Test has " + str(passed_steps) + " passed teststeps")

        # go through steps
        stepcnt = 0
        for teststep in test.findall("test_step"):
            step_id = int(teststep.get('id'))
            # print("\tVerifying step " + str(step_id))
            node_type = teststep.get('node_type')
            step_status = teststep.find("status").get("status")
            # ###DEBUG#### print("Step " + str(step_id) + " Node=" +node_type + " status=" + step_status )
            # ###DEBUG#### print("From DB:" + dbrows[test_id-1][step_id-1][2])
            if step_id != int(dbrows[test_id-1][step_id-1][1]):
                errorCnt += 1
                errorText += print_return_error(
                    "mismatch between step id from DB and XML:" + dbrows[test_id-1][step_id-1][1] + "<>" + str(step_id))
            if node_type != dbrows[test_id-1][step_id-1][2]:
                errorCnt += 1
                errorText += print_return_error("mismatch between node types from DB and XML:" + node_type + "<>" +
                      dbrows[test_id - 1][step_id - 1][2])
            if step_status != "PASS":
                errorCnt += 1
                errorText += print_return_error("status is not pass for step " + str(step_id))


    if errorCnt > 0 :
        logLineData.append("FAIL")
        logLineData.append(errorText)
    else :
        logLineData.append("PASS")
        logLineData.append(str(testCnt) + " tests passed")
    logData.append(logLineData)

# finalize output
auto_report = "<html><head><title>Test Automation Execution Report</title></head><body>"
auto_report += tabulate(logData,headers=["Test case name","JIRA Reference","Result",'Explanation'],tablefmt='unsafehtml')
auto_report += "</body></html>"
print(auto_report)

# write file
f=open("c:\\test\\test_report.html","w")
f.write(auto_report)
f.close()




