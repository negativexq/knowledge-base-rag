# HOLDOUT Zero-Recall / Budget-Exhausted Samples

## techqa_DEV_Q126#row-0066

Question: Why is WebSphere MQ connection failing when enabling SSL with AMQ9640 SSLPEER peer name error? Why is WebSphere MQ connection failing when enabling SSL with AMQ9640 SSLPEER peer name error?
example client side error:com.ibm.mq.jmqi.JmqiException: CC=2;RC=2399;
 
AMQ9640: SSL invalid peer name, channel '?',
 
attribute 'OID.0.9.2342.19200300.100.1.3 (x2)'.

Gold sources: ragbench_techqa_doc_bd329e13ab23f43b

Gold annotation keys: 3g, 3h, 3i, 3l, 3m

Gold annotation `3g`: This fails with a

Gold annotation `3h`:    JMSException, with reason code MQRC_SSL_PEER_NAME_ERROR.

Gold annotation `3i`:    The exception is similar to:

Selected evidence source IDs:
- ON: ragbench_techqa_doc_0b1899649bf5218b, ragbench_techqa_doc_29e02b10047025f2, ragbench_techqa_doc_4f14561a268598eb, ragbench_techqa_doc_55c4b15dd4abb9a2, ragbench_techqa_doc_795f71f869a88b37
  excerpt: 720limitation; MQ; CERTLABL; 2539; 0x000009eb; MQRC_CHANNEL_CONFIG_ERROR TECHNOTE (TROUBLESHOOTING)  PROBLEM(ABSTRACT)  After setting CERTLABL for an SSL channel on MQ Server, DataPower can no longer connect to that channel.  SYMPTOM When CERTLABL is configured on the channel tha SUBSCRIBE You can track all active APARs for this component.  APAR STATUS  * CLOSED AS PROGRAM ERROR.  ERROR DESCRIPTION  *  When using the WebSphere MQ v7.5 classes for JMS or classes for    Java to connect to an IBM MQ v8 queue manager that has the    Advanced Message Security 
- OFF: ragbench_techqa_doc_0b1899649bf5218b, ragbench_techqa_doc_4f14561a268598eb, ragbench_techqa_doc_55c4b15dd4abb9a2, ragbench_techqa_doc_795f71f869a88b37, ragbench_techqa_doc_e58a14cf806268bf
  excerpt: 720limitation; MQ; CERTLABL; 2539; 0x000009eb; MQRC_CHANNEL_CONFIG_ERROR TECHNOTE (TROUBLESHOOTING)  PROBLEM(ABSTRACT)  After setting CERTLABL for an SSL channel on MQ Server, DataPower can no longer connect to that channel.  SYMPTOM When CERTLABL is configured on the channel tha SUBSCRIBE You can track all active APARs for this component.  APAR STATUS  * CLOSED AS PROGRAM ERROR.  ERROR DESCRIPTION  *  When using the WebSphere MQ v7.5 classes for JMS or classes for    Java to connect to an IBM MQ v8 queue manager that has the    Advanced Message Security 

Deterministic outcome: `CORPUS_MISSING` precedes downstream retrieval interpretation; no relevant gold source is indexed.

## techqa_DEV_Q277#row-0042

Question: Is transient user support available for SAML integration with WebSphere Portal 8.0? I am looking to leverage the SAML TAI provided by WebSphere Application Server for my WebSphere Portal 8.0 environment. Is transient user support available so that I do not have to maintain a local account in my Portal user registry for every external user which is verified and trusted by my identity provider? 

Gold sources: ragbench_techqa_doc_4fb3e7c642ac17de

Gold annotation keys: 0r, 0s

Gold annotation `0r`: Transient user support [http://www-01.ibm.com/support/knowledgecenter/SSHRKX_8.5.0/mp/overview/new_cf08.dita?lang=en] has been introduced for SAML TAI [http://www-01.ibm.com/support/knowledgecenter/SSHRKX_8.5.0/mp/wcm/wcm_secure_int_tai_auth.dita?lang=en] starting with Cumulative Fix (CF) #8 for 8.5.

Gold annotation `0s`: Refer to the WebSphere Portal Security blog [https://www.ibm.com/developerworks/community/blogs/8f2bc166-3bdc-4a9d-bad4-3620dbb3e46c/entry/portal_transient_user_support_with_was_saml_tai_business_case_clarification?lang=en] for more details regarding the business case and implementation details.

Selected evidence source IDs:
- ON: ragbench_techqa_doc_18495322ec83be24, ragbench_techqa_doc_793a3c9a7d0ba85e, ragbench_techqa_doc_7b27399ac855a98e, ragbench_techqa_doc_bb7dcc7f00ea6ab9, ragbench_techqa_doc_f177f134be8a09b2
  excerpt: SECURITY BULLETIN  SUMMARY  IBM WebSphere Application Server is shipped as a component of IBM WebSphere Portal. Information about security vulnerabilities affecting IBM WebSphere Application Server has been published in security bulletins.  VULNERABILITY DETAILS Please consult th SECURITY BULLETIN  SUMMARY  Vulnerability in Apache Commons FileUpload affects IBM WebSphere Service Registry and Repository (CVE-2016-1000031)  VULNERABILITY DETAILS CVEID: CVE-2016-1000031 [http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2016-1000031] DESCRIPTION: Apache Comm
- OFF: ragbench_techqa_doc_18495322ec83be24, ragbench_techqa_doc_56176d3b8b68ff5b, ragbench_techqa_doc_5d2ab43a51acca3d, ragbench_techqa_doc_7b27399ac855a98e, ragbench_techqa_doc_f21020d0afc3b0eb
  excerpt: TECHNOTE (FAQ)  QUESTION  What is changing in the Infosphere Information Server support experience?  CAUSE We are always striving to seek new and better ways to improve our communications and the support we offer. With that in mind, we’re excited to announce we’re launching a new ClearCase; ALBD; 1296744 TECHNOTE (FAQ)  QUESTION  Is it possible to use two different IBM® Rational® ClearCase® privileged user (clearcase_albd) accounts for accessing the VOB server?  CAUSE  You want to use two different albd accounts for accessing your VOB server.  You want to

Deterministic outcome: `CORPUS_MISSING` precedes downstream retrieval interpretation; no relevant gold source is indexed.

## techqa_DEV_Q250#row-0012

Question: Help with Security Bulletin: IIB is affected by Node.js security vulnerability ( CVE-2017-1000381 and CVE-2017-11499 ) I need to understand details regarding Security Bulletin: IBM Integration Bus is affected by Node.js security vulnerability ( CVE-2017-1000381 and CVE-2017-11499 ). Where can I find this information? 

Gold sources: ragbench_techqa_doc_e238c28988367e10

Gold annotation keys: 3x, 3y, 3z, 3ae, 3af, 3ag

Gold annotation `3x`: CVEID: CVE-2017-1000381 [http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2017-1000381]

Gold annotation `3y`: DESCRIPTION: c-ares could allow a remote attacker to obtain sensitive information, caused by an out-of-bounds read in the ares_parse_naptr_reply() function when parsing NAPTR responses.

Gold annotation `3z`: By sending specially crafted DNS response packet, an attacker could exploit this vulnerability to read memory outside of the given input buffer and cause a denial of service.

Selected evidence source IDs:
- ON: ragbench_techqa_doc_003b1db2a5df94df, ragbench_techqa_doc_8b166ef73e798145, ragbench_techqa_doc_9589d3195a4ea79a, ragbench_techqa_doc_c43d0294110e044c, ragbench_techqa_doc_e185c812fa88d895
  excerpt: SECURITY BULLETIN  SUMMARY  WebSphere Message Brokerで使用されるIBM®ランタイム環境Java™Technology Edition 6.0.16.26（およびそれ以前のバージョン）、WebSphere Message BrokerおよびIBM Integration Busで使用されるIBM®Runtime Environment Java™Technology Edition 7.0.9.40（およびそれ以前のバージョン）、およびIBM Integration Busで使用されるIBM®ランタイム環 WMB IIB SECURITY BULLETIN  SUMMARY  IBM Integration Bus and WebSphere Message Broker SOAP FLOWS are vulnerable to XML external entity attack.  VULNERABILITY DETAILS CVEID: CVE-2016-9706 [http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2016-9706] DESCRIPTION: IBM Integration Bus
- OFF: ragbench_techqa_doc_091a47d4ddf26ecd, ragbench_techqa_doc_793a3c9a7d0ba85e, ragbench_techqa_doc_8b166ef73e798145, ragbench_techqa_doc_9589d3195a4ea79a, ragbench_techqa_doc_c3ffb29dfbca1623
  excerpt: WMB IIB SECURITY BULLETIN  SUMMARY  Multiple security vulnerabilities exist in the IBM® Runtime Environment Java™ Technology Edition 6.0.16.26 (and earlier) used by WebSphere Message Broker, and the IBM® Runtime Environment Java™ Technology Edition 7.0.9.40 (and earlier) used by  WMB IIB SECURITY BULLETIN  SUMMARY  WebSphere Message Broker and IBM Integration Bus; web user interface error page returns detailed error information.  VULNERABILITY DETAILS  CVE-ID: CVE-2014-4819 CVSS Base Score: 4 CVSS Temporal Score: See https://exchange.xforce.ibmcloud.com/v

Deterministic outcome: `CORPUS_MISSING` precedes downstream retrieval interpretation; no relevant gold source is indexed.

## techqa_DEV_Q275#row-0091

Question: Jobtask long description How do I modify the JP sheet to include the JOBTASK Long description in the query.  I have tried JOBTASK.DESCRIPTION.DESCRIPTION_LONGDESCRITION and other combinations but they do not seem to work. 

Gold sources: ragbench_techqa_doc_97c8628e5eebb265

Gold annotation keys: 3k, 3l, 3m, 3n, 3o, 3p

Gold annotation `3k`: SELECT JOBPLANID FROM JOBPLAN WHERE JPNUM='IT-ISSUE'

Gold annotation `3l`: output: JOBPLANID = 51

Gold annotation `3m`: Then take output from the query above and put it in the query below:

Selected evidence source IDs:
- ON: ragbench_techqa_doc_40cbd32df674b273, ragbench_techqa_doc_45ba8696026db647, ragbench_techqa_doc_ba0d85b79a1c08d7, ragbench_techqa_doc_bb7dcc7f00ea6ab9, ragbench_techqa_doc_cec40b3378d99452
  excerpt: SUBSCRIBE You can track all active APARs for this component.  APAR STATUS  * CLOSED AS DOCUMENTATION ERROR.  ERROR DESCRIPTION  *  This APAR describes the issues that customers encountered with    IBM WebSphere Application Server Version 8.5. These issues were    resolved as info SUBSCRIBE You can track all active APARs for this component.  APAR STATUS  * CLOSED AS PROGRAM ERROR.  ERROR DESCRIPTION  *  When  attempting to issue a long-running command scheduler    command using lrcmd.[bat|sh] through the On-Demand Router (ODR),    an IOException will be re
- OFF: ragbench_techqa_doc_45ba8696026db647, ragbench_techqa_doc_5bc6bf0a5f6b6908, ragbench_techqa_doc_b6419707a88fc9a1, ragbench_techqa_doc_b976c9fecc781b97, ragbench_techqa_doc_cec40b3378d99452
  excerpt: PRODUCT README  ABSTRACT  This readme file contains information about installation of the interim fix and about known problems, restrictions, and solutions in support of IBM® Datacap Version 9.1.3.  CONTENT  Note: To view other versions of IBM Datacap 9.1.3 Interim Fixes readme f plug-in; plugin; GSKIT; GSKIT5; GSKIT6; GSKIT7; recommendations was app server TECHNOTE (TROUBLESHOOTING)  PROBLEM(ABSTRACT)  Which version of Plug-in can be used with which version of WAS?  RESOLVING THE PROBLEM  Supported combinations of IBM HTTP Server, WebSphere Application S

Deterministic outcome: `CORPUS_MISSING` precedes downstream retrieval interpretation; no relevant gold source is indexed.

## techqa_DEV_Q218#row-0137

Question: Why is MQ pattern showing installed MQ version as 8.0.0.2, instead of 8.0.0.4 when client tries to deploy pattern at the MQ 8.0.0.4 version in PureApplication System? In the pattern, it was clearly showing MQ version 8.0.0.4. After deployment, client checked the MQ version on the Virtual Machine and it shows 8.0.0.2 instead.


Gold sources: ragbench_techqa_doc_1bf7d637508864f4

Gold annotation keys: 1b, 1g, 1h, 1m

Gold annotation `1b`:  Users observe errors when attempting to install or migrate to IBM MQ 8.0.0.4 using IBM Pure Application System. SYMPTOM

Gold annotation `1g`: Because of an interface change in IBM Pure Application System 2.1.2.0, and in 2.2.0.0 and greater, installation and upgrade of IBM MQ at the latest maintenance level contained in the pattern-type fails.

Gold annotation `1h`: The installation appears to succeed, but IBM MQ 8.0.0.2 is installed and the subsequent fixpack update is not applied.

Selected evidence source IDs:
- ON: ragbench_techqa_doc_6ae7ec456d8b1b9a, ragbench_techqa_doc_795f71f869a88b37, ragbench_techqa_doc_8b166ef73e798145, ragbench_techqa_doc_a3c52607873592d1
  excerpt: WMB IIB SECURITY BULLETIN  SUMMARY  Multiple security vulnerabilities exist in the IBM® Runtime Environment Java™ Technology Edition 6.0.16.26 (and earlier) used by WebSphere Message Broker, and the IBM® Runtime Environment Java™ Technology Edition 7.0.9.40 (and earlier) used by  WMB IIB SECURITY BULLETIN  SUMMARY  Multiple security vulnerabilities exist in the IBM® Runtime Environment Java™ Technology Edition Version 6 Service Refresh 16 Fix Pack 41 and earlier releases used by WebSphere Message Broker, and the IBM® Runtime Environment Java™ Technology E
- OFF: ragbench_techqa_doc_0c6d237f95b86c61, ragbench_techqa_doc_6629999893db7c3e, ragbench_techqa_doc_795f71f869a88b37, ragbench_techqa_doc_92287865465b3609, ragbench_techqa_doc_a3c52607873592d1
  excerpt: SUBSCRIBE You can track all active APARs for this component.  APAR STATUS  * CLOSED AS PROGRAM ERROR.  ERROR DESCRIPTION  *  Customer has uploaded the following IBM WebSphere SDK Java    Technology Edition 7.1 fix package to the IBM Installation    Manager Repository on the PureA create an empty directory (with sufficient space to receive the download file) and make it current.  2. Download mqc8_platform to this directory. (Where 'platform' is replaced with a specific platform name e.g. AIX, Linux-x86) 3. Uncompress mqc8_platform. 4. Execute tar -xvf mqc8

Deterministic outcome: `CORPUS_MISSING` precedes downstream retrieval interpretation; no relevant gold source is indexed.

