"""
/                               GET              First page of the listing of all links
/page/[num]                     GET              [num] page of the listing of all links
/tag/[tag]                      GET              First page of the listing of links tagged [tag]
/tag/[tag]/[num]                GET              [num] page of the listing of links tagged [tag]
/static/*                       GET              Static files (css, images, javascript)
/new                            GET              Add new link form
/save                           POST             Save a link (post from edit or new forms)
/edit                           GET              Edit a link form
/reading-list                   GET              Get the reading list of the current user
/reading-list/add/[link_id]     GET              Add [link_id] to the current user's reading list
/reading-list/read/[link_id]    GET              Mark [link_id] as read for the current user's reading list
"""

from webob import Response, Request
import pystache
from urllib import parse
import re
import os
import base64

from pkg_resources import resource_filename
import mimetypes

from . import wrapper
from . import schema
from jsonschema import Draft3Validator


class BadRequest(Exception):
    """
    Raised when something bad happened in a request
    """
    
    def __init__(self, msg="Bad Request", code=400):
        self.msg = msg
        self.code = code
        
    def __str__(self):
        return self.msg
        
        
    def __call__(self, environ, start_response):
        res = Response(self.msg, status=self.code)
        return res(environ, start_response)
    
class NotFound(BadRequest):
    """
    Raised when something is not found.
    """
    def __init__(self, msg="Not Found", code=404):
        BadRequest.__init__(self, msg, code)

class Redirect(BadRequest):
    def __init__(self, path, code=302):
        self.path = path
        self.code = code
        
    def __call__(self, environ, start_response):
        url = 'http://%s%s' % (environ['HTTP_HOST'], self.path)
        
        res = Response(url, status=self.code)
        
        res.headers['location'] = url
        
        return res(environ, start_response)
        
class BackEndTrouble(BadRequest):
    def __init__(self, msg="Some trouble with the back-end. Please try your request again later", code=400):
        BadRequest.__init__(self, msg, code)
        
class TooManyRetries(BackEndTrouble):
    pass
        
class Unauthorized(BadRequest):
    """
    Raised when a bad content type is specified by the client.
    """
    def __init__(self, msg="Unauthorized", code=401, realm="Linkapp Microservices"):
        BadRequest.__init__(self, msg, code)
        self.realm = realm
        
    def __call__(self, environ, start_response):
        res = Response(self.msg, status=self.code)
        res.headers['www-authenticate'] = 'Basic realm={}'.format(self.realm)
        
        return res(environ, start_response)


class GatewayService:
    
    def __init__(self, config):
        self.config = config
        self.link_service = wrapper.ServiceWrapper(config.link_service_url)
        self.tag_service = wrapper.ServiceWrapper(config.tag_service_url)
        self.authentication_service = wrapper.ServiceWrapper(config.authorization_service_url)
        self.readinglist_service = wrapper.ServiceWrapper(config.readinglist_service_url)
        
        self.renderer = pystache.Renderer(search_dirs=resource_filename("linkapp.gateway", "templates"), file_extension='html')
        
        self.static_path = resource_filename("linkapp.gateway", "static")
        
        self.path_map = {
            re.compile("^/(page/(?P<page>\d+))?$"): self.listing,
            re.compile("^/tag/(?P<tag>[^/]+)(/page/(?P<page>\d+))?$"): self.listing_by_tag,
            re.compile("^/static/(?P<path>.*)$"): self.static,
            re.compile("^/new$"): self.new,
            re.compile("^/reading-list$"): self.reading_list,
            re.compile("^/reading-list/add/?(?P<link_id>[^/]{32})?$$"): self.reading_list_add,
            re.compile("^/reading-list/read/?(?P<link_id>[^/]{32})?$$"): self.reading_list_read,
            re.compile("^/edit/?(?P<link_id>[^/]{32})?$"): self.edit,
            re.compile("^/save/?(?P<link_id>[^/]{32})?$"): self.save,
            re.compile("^/view/?(?P<link_id>[^/]{32})?$"): self.view,
        }
        
    def authorize(self, req):
        if req.authorization:
            auth_type, hashed_pass = req.authorization
            
            decoded = base64.b64decode(hashed_pass)
            
            username, password = decoded.decode('utf-8').split(':')
            
            print(decoded)
            
            try:
                if not self.authentication_service.post("/{}".format(username), password):
                    raise Unauthorized()
                else:
                    res = Response()
                    res.set_cookie('linkapp.username', username, path='/')
                    
                    return res
            except wrapper.Unauthorized:
                raise Unauthorized()
        else:
            raise Unauthorized()
        
    def __call__(self, environ, start_response):
        req = Request(environ)
        
        req = Request(environ, charset="utf8")
        
        new_path = parse.unquote(req.path)
        
        res = None
        
        try:
            for regexp, method in self.path_map.items():
                match = re.match(regexp, new_path)
                if match:
                    print(match.groupdict())
                    res = method(req, **match.groupdict())
                    break
            
            if res is None:
                raise NotFound()
            
        except BadRequest as e:
            return e(environ, start_response)
        
        return res(environ, start_response)
     
    def view(self, req, link_id):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        try:
            link = self._getlink(link_id)
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.NotFound:
            raise NotFound()
        except wrapper.BadRequest:
            raise BackEndTrouble()
        
        context = {
            'one_post': link,
            'prefix': self.config.path_prefix,
            'key': link_id
        }
        
        res = Response()
        res.text = self.renderer.render_name('one_post', context)
        
        return res
     
    def new(self, req):
        res = self.authorize(req)
        
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        context = {
           'prefix': self.config.path_prefix, 
           'link':True
        }
        
        res.text = self.renderer.render_name('form', context)
        
        return res
        
    def edit(self, req, link_id):
        res = self.authorize(req)
        
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        try:
            link = self._getlink(link_id)
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.NotFound:
            raise NotFound()
        except wrapper.BadRequest:
            raise BackEndTrouble()
        
        link['tags'] = "|".join([t['name'] for t in link['tags']])
        
        context = {
           'prefix': self.config.path_prefix, 
           'link': link,
           'key': link_id
        }
        
        res.text = self.renderer.render_name('form', context)
        
        return res
        
    def save(self, req, link_id=None):
        res = self.authorize(req)
        
        if req.method != "POST":
            raise BadRequest("Bad Request, Method not supported")
        
        data = req.POST.mixed()
        
        data['author'] = req.cookies['linkapp.username']
        
        errors = []
        
        page_title = data.get('page_title', None)
        if page_title is None or page_title == '':
            errors.append({'message':b'Page Title Required'})
        
        desc_text = data.get('desc_text', None)
        if desc_text is None or desc_text == '':
            errors.append({'message':b'Description Required'})
        
        url_address = data.get('url_address', None)
        if url_address is None or url_address == '':
            errors.append({'message':b'URL is a required field'})
            
        tags = data.get('tags', None)
    
        if tags is None or tags == '':
            errors.append({'message':b'Please enter at least one tag.'})
        else:
            process_tags = list(set([x.strip() for x in tags.split('|')]))
            
        if not errors:
            try:
                if link_id:
                    self.link_service.put("/{}".format(link_id), data)
                    self.tag_service.put("/link/{}".format(link_id), {'tags':process_tags})
                else:
                    link_id = self.link_service.post("/", data)
                    self.tag_service.post("/link/{}".format(link_id), {'tags':process_tags})
                
            except wrapper.BadRequest as e:
                errors.append({"message":str(e)})
            except wrapper.TooManyRetries as e:
                errors.append({"message":"Trouble with the back-end. Please try again later"})
                
                
        if errors:
            context = {
                'errors': errors,
                'link': data,
                'prefix': self.config.path_prefix,
                'key': link_id
            }
            
            res.text = self.renderer.render_name('form', context)
            
            return res
        else:
            raise Redirect(path=self.config.path_prefix)
    
    def _getlink(self, link_id, process_tags=True):
        link = self.link_service.get("/{}".format(link_id))
                
        tags = self.tag_service.get("/link/{}".format(link_id))
                
        link['tags'] = [{"name": x} for x in tags]
        link['key'] = link_id
        
        return link
    
    def listing(self, req, page=None):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        if not page:
            page = 1
        else:
            page = int(page)
        
        links = []
        
        try:
            data = self.link_service.get("/?page={}".format(page))
            
            for link_id in data['links']:
                link = self._getlink(link_id)
                
                links.append(link)
            
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.BadRequest:
            raise BackEndTrouble()
        
        context = { 
            'links': links,
            'count': data['pagination']['count'],
            'last': data['pagination']['last'],
            'prefix': self.config.path_prefix,
            'user': req.cookies.get('linkapp.username')
        }
        
        if page > 1:
            # making previous a string so mustache won't think its false.
            context['previous'] = data['pagination']['previous']
            
        if page != data['pagination']['last']:
            context['next'] = data['pagination']['next']
        
        res = Response()
        res.text = self.renderer.render_name('list', context)
        
        return res
        
    def static(self, req, path):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        to_get = os.path.join(self.static_path, path)
        
        if os.path.isfile(to_get):
            def serve_file(environ, start_response):
                content_type, encoding = mimetypes.guess_type(to_get)
                
                start_response('200 OK', [('Content-Type', content_type)])
                
                block_size = 4096
                
                asset = open(to_get, 'rb')
                
                # lifted from pep 333: https://www.python.org/dev/peps/pep-0333/#optional-platform-specific-file-handling
                if 'wsgi.file_wrapper' in environ:
                    return environ['wsgi.file_wrapper'](asset, block_size)
                else:
                    return iter(lambda: asset.read(block_size), '')
                    
            return serve_file
        else:
            raise NotFound()
        
    def listing_by_tag(self, req, tag, page=None):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        res = Response()
        
        if not page:
            page = 1
        else:
            page = int(page)
        
        links = []
        
        try:
            data = self.tag_service.get("/tag/{}?page={}".format(tag, page))
            
            for link_id in data['links']:
                link = self._getlink(link_id)
                
                links.append(link)
            
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.BadRequest:
            raise BackEndTrouble()
        
        context = { 
            'links': links,
            'count': data['pagination']['count'],
            'last': data['pagination']['last'],
            'prefix': self.config.path_prefix,
            'user': req.cookies.get('linkapp.username'),
            'tag': tag
        }
        
        if page > 1:
            # making previous a string so mustache won't think its false.
            context['previous'] = data['pagination']['previous']
            
        if page != data['pagination']['last']:
            context['next'] = data['pagination']['next']
        
        res = Response()
        res.text = self.renderer.render_name('list', context)
        
        return res
                    
    def reading_list(self, req):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        res = self.authorize(req)
        
        user = req.cookies.get('linkapp.username')
        
        links = []
        
        try:
            data = self.readinglist_service.get("/{}".format(user))
            
            for link_id in data:
                link = self._getlink(link_id)
                
                links.append(link)
            
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.BadRequest:
            raise BackEndTrouble()
            
        context = {
            "user":user,
            'prefix': self.config.path_prefix,
            "links": links
        }
            
        res.text = self.renderer.render_name('reading-list', context)
            
        return res
        
    def reading_list_add(self, req, link_id):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        res = self.authorize(req)
        
        user = req.cookies.get('linkapp.username')
        
        try:
            data = self.readinglist_service.post("/{}".format(user), link_id)
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.BadRequest:
            raise BackEndTrouble()
            
        return Redirect(path=self.config.path_prefix+"reading-list")
        
    def reading_list_read(self, req, link_id):
        if req.method != "GET":
            raise BadRequest("Bad Request, Method not supported")
        
        res = self.authorize(req)
        
        user = req.cookies.get('linkapp.username')
        
        try:
            data = self.readinglist_service.put("/{}/{}/read".format(user, link_id))
        except wrapper.TooManyRetries:
            raise TooManyRetries()
        except wrapper.BadRequest:
            raise BackEndTrouble()
            
        return Redirect(path=self.config.path_prefix+"reading-list")