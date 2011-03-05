import urllib, urllib2, httplib2
from elementtree.ElementTree import XML, Element, SubElement, dump
import pprint
from django.conf import settings
from projects.models import *
import poster

# todo: error handling

class CafepressClient(object):
    def __init__(self):
        self.storeId = settings.CAFEPRESS_STORE_ID
        self.apiKey = settings.CAFEPRESS_API_KEY
        self.apiBase = settings.CAFEPRESS_API_BASE
        self.uploadBase = settings.CAFEPRESS_UPLOAD_BASE
        self.apiVersion = '3'
        self.username = settings.CAFEPRESS_USERNAME
        self.password = settings.CAFEPRESS_PASSWORD
        self.userToken = None
        self.http = httplib2.Http()

    def call(self, action, params = {}, useAppKey = True, useToken = False, method = 'GET', debug=False, hasFiles = False):
        url = self.uploadBase if hasFiles else self.apiBase
        url += action + '.cp'
        params['v'] = self.apiVersion

        if useAppKey:
            params['appKey'] = self.apiKey
        if useToken:
            params['userToken'] = self.getUserToken()

        headers = {}
        datagen = ''
        if len(params):
            if method == 'POST':
                if hasFiles:
                    import poster
                    poster.streaminghttp.register_openers()
                    datagen, headers = poster.encode.multipart_encode(params)
                else:
                    datagen = urllib.urlencode(params)
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
            else:
                url += '?' + urllib.urlencode(params)

        request = urllib2.Request(url, datagen, headers)
        content = urllib2.urlopen(request).read()

        # todo: check resp error code (if useToken then try another token)
        if debug:
          print content

        return XML(content)

    def getUserToken(self):
        if self.userToken is None:
            content = self.call('authentication.getUserToken', {'email': self.username, 'password': self.password})
            self.userToken = content.text
        return self.userToken

    def uploadImage(self, imagePath):
        params = {'cpFile1': open(imagePath, 'rb'), 'folder': 'Images'}
        content = self.call('image.upload', params, useToken = True, method = 'POST', hasFiles = True)
        designId = content.findtext('value')
        return designId
        
    def createDesign(self, svg):
        # todo: look into poster.streaminghttp to stream uploaded svgs directly
        content = self.call('design.save', params = {'value': '<?xml version="1.0"?><design />', 'svg': svg}, useToken = True, method = 'POST')
        designId = content.attrib['id']
        return designId
    
    def createProduct(self, merchandiseId, name, media, perspectiveName = 'Front', colors = []):
        product = '<?xml version="1.0"?><product name="' + name.replace('"', '&quot;') + '" merchandiseId="' + str(merchandiseId) + '" storeId="' + self.storeId + '">'
        for designId, mediaRegion in media:
            product += '<mediaConfiguration dpi="' + str(mediaRegion.dpi) + '" name="' + mediaRegion.name + '" designId="' + str(designId) + '" />'

        defaultColor = None
        if colors:
          for color, default in colors:
            product += '<color id="' + str(color) + '" default="'
            product += 'true' if default else 'false'
            product += '"/>'

            if default:
              defaultColor = color

        product += '</product>'
        content = self.call('product.save', params = {'value': product}, useToken = True, debug=False)

        product = {
            'cafepressId': content.attrib['id'],
            'storeUri': content.attrib['storeUri'],
            'name': name
        }

        for image in content.getiterator('productImage'):
            if image.attrib['perspectiveName'] == perspectiveName and (defaultColor is None or image.attrib['colorId'] == str(defaultColor)):
                product['image'] = image.attrib['productUrl'];
                break

        return product

    def updateMerchandise(self, merchandise):
      content = self.call('merchandise.find', params = {'id': merchandise.cafepressId, 'userId': 1}, useToken = True)

      # base attributes
      merchandise.basePrice = content.attrib['basePrice']
      merchandise.wildcardBlankProductUrl = content.attrib['wildcardBlankProductUrl']

      # MediaRegions
      existingRegions = dict([(region.name, region) for region in merchandise.mediaregion_set.all()])
      for newRegion in content.getiterator('mediaRegion'):
        if newRegion.attrib['name'] in existingRegions:
          mediaRegion = existingRegions[newRegion.attrib['name']]
          del existingRegions[newRegion.attrib['name']]
        else:
          mediaRegion = MediaRegion()
          mediaRegion.merchandise = merchandise
          mediaRegion.name = newRegion.attrib['name']
        dpi = int(newRegion.attrib['dpi'])
        mediaRegion.width = float(newRegion.attrib['width']) * dpi
        mediaRegion.height = float(newRegion.attrib['height']) * dpi
        mediaRegion.dpi = newRegion.attrib['dpi']
        mediaRegion.save()
      for id, region in existingRegions:
        region.delete()

      # Colors
      existingColors = dict([(str(color.cafepressId), color) for color in merchandise.color_set.all()])
      for newColor in content.getiterator('color'):
        if newColor.attrib['id'] in existingColors:
          color = existingColors[newColor.attrib['id']]
          del existingColors[newColor.attrib['id']]
        else:
          color = Color()
          color.merchandise = merchandise
          color.cafepressId = newColor.attrib['id']
        color.name = newColor.attrib['name']
        color.isDefault = newColor.attrib['default'] == 'true'
        color.swatchUrl = newColor.attrib['colorSwatchUrl']
        color.save()
      for id, color in existingRegions:
        color.delete()

      merchandise.save()
      return merchandise

