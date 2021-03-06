import os
import sys
import time
import datetime
import logging
import commands

try:
    import OpenSSL
    from OpenSSL import crypto
    vers = OpenSSL.version.__version__
    major, minor = str(vers).split('.')[:2]
    intmajor = int(major)
    intminor = int(minor)
    if intmajor < 1 and intminor < 7:
        print "Incompatible verions %s.%s: This plugin requires pyOpenSSL >= 0.7" % (intmajor, intminor)
        sys.exit(0)   
except ImportError:
    print  "Import error: this plugin requires pyOpenSSL >= 0.7"
    sys.exit(0)
    
from certify.core import CertifyCertInterface

class OpenSSLCertPlugin(CertifyCertInterface):
    '''
     Uses the openssl command line program to create Requests and handle certificates. 
    
    '''
      
    def __init__(self, certhost):
        super(OpenSSLCertPlugin, self).__init__(certhost)
        self.log = logging.getLogger()
        self.certhost = certhost
        self.log.debug("[%s:%s] Begin..." % ( self.certhost.hostname, self.certhost.service))
        self.certhost = certhost
        self.pkey = None  # X509.PKey object
        self.tempsslconffile="%s%s/%sssl.conf" % (self.certhost.temproot, 
                                               self.certhost.targetdir, 
                                               self.certhost.service )
        # Put the ssl conf file wherever the cert file will go:
        (self.certdir, basename) = os.path.split(self.certhost.certfile)
        self.sslconffile="%s/%sssl.conf" % ( self.certdir, self.certhost.service )
        self.log.debug("[%s:%s] Done." % ( self.certhost.hostname, self.certhost.service))

    def __str__(self):
        s = "OpenSSLCertPlugin [%s:%s]: " % (self.certhost.hostname, self.certhost.service)
        return s
            
    def loadCertificate(self):
        '''
        However necessary, read public certificate into self.certificate from temp dir.
        
        '''
        self.log.debug("[%s:%s] Begin..." % ( self.certhost.hostname, self.certhost.service))
        if os.path.exists(self.certhost.tempcertfile):
            self.log.debug("[%s:%s] Loading cert from %s" % (self.certhost.hostname, 
                                                             self.certhost.service, 
                                                          self.certhost.tempcertfile))
            self._pubcertbuffer = open(self.certhost.tempcertfile).read()
            self.certhost.certificate = crypto.load_certificate(crypto.FILETYPE_PEM, 
                                                                self._pubcertbuffer)

        else:
            self.log.debug("[%s:%s] Cert file %s not found." % ( self.certhost.hostname, 
                                                                 self.certhost.service, 
                                                                 self.certhost.tempcertfile))
            self.certhost.certificate = None

    
    def dumpCertificate(self):
        '''
        Write out self.certificate to self.tempcertfile in temp dir.
         
        '''
        self.log.debug("[%s:%s] Start..." % ( self.certhost.hostname, self.certhost.service))
        # Handle public key
        if self.certhost.certificate and self.certhost.certfile:
            self.log.debug("[%s:%s] Dumping cert to %s" % (self.certhost.hostname,
                                                           self.certhost.service,  
                                                        self.certhost.tempcertfile))    
            (filepath, tail) = os.path.split(self.certhost.certfile)
            if not os.path.exists(filepath):
                os.makedirs(filepath)
            cf = open(self.certhost.tempcertfile, 'w')
            cf.write(crypto.dump_certificate(crypto.FILETYPE_PEM, 
                                             self.certhost.certificate))            
            self.log.debug('[%s:%s] Loaded cert object is %s' % (self.certhost.hostname, 
                                                                 self.certhost.service, 
                                                              self.certhost.certificate))
        else:
            self.log.debug("[%s:%s] Cert = None or no certfile set." % ( self.certhost.hostname, self.certhost.service))
        
        # Handle private key
        if self.certhost.privatekey and self.certhost.keyfile:
            self.log.debug("[%s:%s] Dumping key to %s" % (self.certhost.hostname,
                                                          self.certhost.service,  
                                                       self.certhost.keyfile))    
            (filepath, tail) = os.path.split(self.certhost.keyfile)
            if not os.path.exists(filepath):
                os.makedirs(filepath)
            cf = open(self.certhost.keyfile, 'w')
            cf.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, 
                                            self.certhost.keypair))            
            #self.log.debug('[%s:%s] Dumped key to %s' % (self.certhost.hostname, 
            #                                             self.certhost.service, 
            #                                          self.certhost.keyfile))
        else:
            self.log.debug("[%s:%s] Cert = None or no certfile set." % ( self.certhost.hostname, self.certhost.service))

                     
    def validateCert(self):
        '''
        Runs set of tests to validate cert. Failure should trigger renewal/creation.

        '''
        aaa = self._validateCommonName()
        bbb = self._validateCertPair()
        
        if aaa and bbb:
            return True
        else:
            return False
        

    def _validateCommonName(self):
        '''
        Checks to be sure that the current certificate for host is in fact 
        what is specified by hosts.conf. 
        
        1) certificate commonName should be "full.hostname.com" for host
        "service/full.hostname.com" for service cert
        
        2) ?
        
        '''
        self.log.debug("[%s:%s] Start..." % ( self.certhost.hostname, self.certhost.service))
        hname = self.certhost.certificate.get_subject().commonName
        self.log.debug("[%s:%s] commonName is %s" % ( self.certhost.hostname, 
                                                      self.certhost.service, 
                                                      hname)
                                                      )
        if hname == self.certhost.commonname:
            retval=True
            self.log.debug("[%s:%s] Cert commonname '%s' matches that desired '%s'." % ( self.certhost.hostname, 
                                                                                         self.certhost.service,
                                                                                         hname,
                                                                                         self.certhost.commonname
                                                                                         ))
        else:
            self.log.info("[%s:%s] Cert commonname doesn't match that desired. Make new cert." % ( self.certhost.hostname, self.certhost.service))
            retval=False
        self.log.debug("[%s:%s] Done." % ( self.certhost.hostname, self.certhost.service))
        return retval
    
    def _validateCertPair(self):
        '''
         Checks to be sure certificate and private key go together. 
        Uses command:
        
        ( /usr/bin/openssl x509 -noout -modulus -in /etc/grid-security/hostcert.pem | /usr/bin/openssl md5 ; \
        /usr/bin/openssl rsa -noout -modulus -in /etc/grid-security/hostkey.pem | /usr/bin/openssl md5 ) | uniq | wc -l
        
        '''
        try:
            a = self.certhost.ioplugin.executeCommand(cmd)
            return True
        except Exception:
            pass
        return True
    
    
    
                      
    def getExpirationUTC(self):
        '''
        Extracts the certificate expiration date/time and returns an
        equivalent Python datetime object. 
        
        '''
        self.log.debug("[%s:%s] Running..." % ( self.certhost.hostname, self.certhost.service))
        # notAfter String. E.g. 20090731214746Z
        nastr = self.certhost.certificate.get_notAfter()
        if len(nastr) > 12:
            yr=int(nastr[0:4])
            mo=int(nastr[4:6])
            dy=int(nastr[6:8])
            hr=int(nastr[8:10])
            mn=int(nastr[10:12])
            sc=int(nastr[12:14])
            notafter = datetime.datetime(yr, mo, dy, hr, mn,sc,0, tzinfo=None)
            self.log.debug("[%s:%s] Certificate not valid after: %s" % (self.certhost.hostname, self.certhost.service, notafter))
            return notafter
        else:
            self.log.error("[%s:%s] Something horribly wrong with OpenSSL date output: %s" % (self.certhost.hostname,self.certhost.service,  nastr))
               
               
    def _loadRequest(self):
        '''
        However necessary, read request into self.certhost.request
        
        '''
        self.log.debug("[%s:%s] Begin..." % ( self.certhost.hostname, self.certhost.service))
        if os.path.exists(self.certhost.tempreqfile):
            self.log.debug("[%s:%s] Loading request from %s" % (self.certhost.hostname, self.certhost.service, 
                                                             self.certhost.tempreqfile))
            self._reqbuffer = open(self.certhost.tempreqfile).read()
            #self.log.debug("[%s:%s] Request buffer is %s" % (self.certhost.hostname,self.certhost.service, 
            #                                              self._reqbuffer))
            self.certhost.request = crypto.load_certificate_request(crypto.FILETYPE_PEM, 
                                                                    self._reqbuffer)
            
            #self.log.debug('[%s:%s] Loaded request object is %s' % (self.certhost.hostname,self.certhost.service, 
            #                                                     self.certhost.request))
        else:
            self.log.debug("[%s:%s] Request file not found at %s." % (self.certhost.hostname, self.certhost.service, 
                                                                   self.certhost.tempreqfile))
            self.certhost.request = None    
          
    def cleanup(self):
        '''
        Cleans up local temporary files for this host.
        '''
        self.log.debug("[%s:%s] Begin..." % ( self.certhost.hostname, self.certhost.service))
        
        self.log.debug("[%s:%s] Done." % ( self.certhost.hostname, self.certhost.service))
          
###################################################################################
#
# Generic methods using IOPlugin methods to perform Request creation.
#
###################################################################################
    def makeRequest(self):
        '''
        Creates standard OpenSSL X509 Request file for use by an admin interface.  
        
        '''
        self.log.debug("[%s:%s] Start..." % ( self.certhost.hostname, self.certhost.service))      
        self._createCertDir()
        self._createRandomFile()
        self._createSslConf()
        self._copySslConf()
        self._createRequest()
        self._retrieveRequest()
        self._loadRequest()
        #self._removeRandomFile()
        self.log.debug("[%s:%s] Done." % ( self.certhost.hostname, self.certhost.service))        
        
        
    def _createRandomFile(self):
        '''
        Create randomfile on host, fill it with text...
        
        '''
        self.log.debug("[%s:%s] Start..." % ( self.certhost.hostname, self.certhost.service))
        (status,output) = self.certhost.ioplugin.executeCommand("mktemp")
        self.randomfile = output.strip()
        self.log.debug("[%s:%s] Making randomfile %s" % ( self.certhost.hostname, 
                                                   self.certhost.service,
                                                   self.randomfile))
        cmd = "/bin/date > %s; ps aux >> %s ; ls -ln /tmp >> %s" % ( self.randomfile, self.randomfile, self.randomfile)
        self.certhost.ioplugin.executeCommand(cmd)
        self.log.debug("[%s:%s] Done." % ( self.certhost.hostname, self.certhost.service))
    
    def _createSslConf(self):
        '''
        Makes a new OpenSSL conf file for this service/host from template.
        
        '''
        self.log.debug('[%s:%s] Start...'% (self.certhost.hostname, self.certhost.service))
        (path, basename) = os.path.split(self.tempsslconffile)
        if not os.path.exists(path):
            os.makedirs(path)
        out_file = open(self.tempsslconffile, "w")
        sslconftxt = '''RANDFILE = %s
policy = policy_match

[ req ]
default_bits = 2048
default_keyfile = %s
distinguished_name = req_distinguished_name
attributes = req_attributes
encrypt_key = no
prompt = no
req_extensions = v3_req

[ req_attributes ]

[ req_distinguished_name ]
1.DC = org
2.DC = doegrids
OU = Services
CN = %s

[ x509v3_extensions ]
nsCertType = 0x40

[ v3_req ]
subjectAltName = %s

''' % (self.randomfile, 
       self.certhost.keyfile, 
       self.certhost.commonname, 
       self.certhost.subjectaltnames)         
        out_file.write(sslconftxt)
        out_file.close()
        self.log.debug('[%s:%s] Done.'% (self.certhost.hostname, self.certhost.service))


    def _copySslConf(self):
        self.log.debug('[%s:%s] Copying SSL Conf file.'% (self.certhost.hostname, 
                                                                  self.certhost.service,
                                                                  ))
        self.certhost.ioplugin.putFile(self.tempsslconffile, self.sslconffile)
        self.log.debug('[%s:%s] Done.'% (self.certhost.hostname, self.certhost.service))
    
    
    def _createRequest(self):
        '''
        Creates request and puts keyfile in <keyfilename>.new
        
        
        '''
        self.log.debug('[%s:%s] Start...'% (self.certhost.hostname, self.certhost.service))
        cmd = "openssl req  -new -config %s -out %s -keyout %s.pk8.new; openssl rsa -in %s.pk8.new -out %s.new ; chmod 400 %s.new ; rm -f %s.pk8.new " % (self.sslconffile,
                                                                       self.certhost.reqfile,
                                                                       self.certhost.keyfile,
                                                                       self.certhost.keyfile,
                                                                       self.certhost.keyfile,
                                                                       self.certhost.keyfile,
                                                                       self.certhost.keyfile)
        self.certhost.ioplugin.executeCommand(cmd)
        self.log.debug('[%s:%s] Done.'% (self.certhost.hostname, self.certhost.service))

    def _createCertDir(self):
        self.log.debug('[%s:%s] Making certificate dir %s'% (self.certhost.hostname, 
                                                             self.certhost.service,
                                                             self.certdir))        
        self.certhost.ioplugin.makeDir(self.certdir)
        self.log.debug('[%s:%s] Done.'% (self.certhost.hostname, self.certhost.service))

    def _retrieveRequest(self):
        self.log.debug('[%s:%s] Retrieving request %s. '% (self.certhost.hostname, 
                                                           self.certhost.service,
                                                           self.certhost.reqfile))
        self.certhost.ioplugin.getRequest()
        self.log.debug('[%s:%s] Done.'% (self.certhost.hostname, self.certhost.service))  
    
    def _removeRandomFile(self):
        self.log.debug('[%s:%s] Removing random file %s'% (self.certhost.hostname, 
                                                           self.certhost.service,
                                                           self.randomfile))
        self.certhost.ioplugin.removeFile(self.randomfile)
        self.log.debug('[%s:%s] Done.'% (self.certhost.hostname, self.certhost.service))
  




    def _createSslConfX(self):
        '''
        Makes a new OpenSSL conf file for this service/host from template.
        
        This version includes subjectAltName(s)
        
        '''
        out_file = open(self.tmpsslconffile, "w")
        sslconftxt = '''RANDFILE = %s
policy = policy_match
[ req ]
default_bits = 2048
default_keyfile = %s
distinguished_name = req_distinguished_name
attributes = req_attributes
encrypt_key = no
prompt = no
x509_extensions = v3_ca
req_extensions = v3_req

[ req_attributes ]
[ req_distinguished_name ]
1.DC = org
2.DC = doegrids
OU = Services
CN = %s

[ x509v3_extensions ]
nsCertType = 0x40

[ v3_req ]
subjectAltNames = %s
''' % (self.randomfile, 
       self.certhost.targetkey, 
       self.certhost.commonname,
       self.certhost.subjectaltnames)         
        out_file.write(sslconftxt)
        out_file.close()







