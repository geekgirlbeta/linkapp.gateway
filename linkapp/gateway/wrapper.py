import requests
import time
from urllib import parse
from requests.auth import HTTPBasicAuth

class TooManyRetries(Exception):
    """
    Raised when a request is retried too many times.
    """
    
class NotFound(Exception):
    """
    Raised when a call to the service returns a 404 status code.
    """
    
class BadRequest(Exception):
    """
    Raised when a call to the service returns a 400 status code.
    """
    
class Unauthorized(Exception):
    """
    Raised when a call to the service returns a 401 unauthorized status code.
    """

def remove_creds(parsed):
    parts = list(parsed)
    parts[1] = parts[1].split("@")[-1]
    
    return parse.urlunparse(parts)

class ServiceWrapper:
    
    def __init__(self, base_url, timeout=2, retries=10, sleep=0.1):
        parsed = parse.urlparse(base_url) 
        
        if parsed.username:
            self.credentials = HTTPBasicAuth(parsed.username, parsed.password)
            base_url = remove_creds(parsed)
        else:
            self.credentials = None
        
        self.base_url = base_url
        self.max_retries = retries
        self.retries = 1
        self.sleep = sleep
        self.timeout = timeout
        
    def wait(self):
        return self.sleep*(self.retries**2)
        
    def _call(self, func, *args, **kwargs):
        if self.credentials:
            kwargs['auth']=self.credentials
        
        print("ARGS:", args)
        print("KWARGS:", kwargs)
        
        if self.retries >= self.max_retries:
            raise TooManyRetries("Maximum retries of {} exceeded".format(self.retries))
            
        try:
            r = func(*args, **kwargs)
            
            if r.status_code == 404:
                raise NotFound()
            if r.status_code == 400:
                raise BadRequest(r.text)
            if r.status_code == 401:
                raise Unauthorized(r.text)
            
            return r
        except requests.exceptions.RequestException:
            time.sleep(self.wait())
            self.retries += 1
            return self._call(func, *args, **kwargs)
        
    def put(self, path, data=None):
        r = self._call(requests.put,
                       "{}{}".format(self.base_url, path),
                       json=data,
                       headers={"content-type": "application/json"},
                       timeout=self.timeout)
        
        return r.json()
        
    def post(self, path, data=None):
        r = self._call(requests.post,
                       "{}{}".format(self.base_url, path),
                       json=data,
                       headers={"content-type": "application/json"},
                       timeout=self.timeout)
            
        return r.json()
        
    def get(self, path="/"):
        r = self._call(requests.get,
                       "{}{}".format(self.base_url, path),
                       headers={"content-type": "application/json"},
                       timeout=self.timeout)
        
        print(r.text)
        
        return r.json()

        