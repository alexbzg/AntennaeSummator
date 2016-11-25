#!/usr/bin/python
#coding=utf-8

from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.internet import reactor
from twisted.web import static
from twisted.python import log
import os, json, logging


from jeromeController import Controller, ControllerProtocol
ControllerProtocol.pingInterval = 10

observer = log.PythonLoggingObserver()                                  
observer.start()
logging.basicConfig( 
        #level = logging.DEBUG, 
        level = logging.ERROR,
        format='%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S' )


appPath = os.path.dirname( os.path.realpath( '__file__' ) )
conf = json.load( open( appPath + '\conf.json', 'r' ) )

defaultSwitch = None
switches = []
clusters = []

class Switch:
    def __init__( self, params ):
        global defaultSwitch
        self.combo = tuple( params['combo'] )
        self.outLinesStates = [ 0, 0, 0, 0 ]
        self.UARTsignal = 0
        for i in self.combo:
            self.UARTsignal |= 1 << ( i - 1 )
        if len( self.combo ) == 1:
            self.outLinesStates[ self.combo[0] - 1 ] = 1
            self.outLinesStates[ 3 ] = 1
        elif len( self.combo ) == 2:
            for i in range(3):
                if not ( i + 1 ) in self.combo:
                    self.outLinesStates[ i ] = 1
        if params.has_key('default') and params['default']:
            defaultSwitch = self
 #       switches[self.combo] = self

class Cluster:
    def __init__( self, params ):
        self.tx = False
        self.title = params['title']
        self.currentSwitch = defaultSwitch
        self.lockSwitch = False
        self.activeDevice = None
        self.terminals = [ Terminal( entry, self ) for entry in params['terminals'] ]
        self.devices = [ Device( entry, self ) for entry in params['controllers'] ]

    def setActiveDevice( self, activeDevice ):
        if self.activeDevice:
            self.activeDevice.disconnect()
        self.activeDevice = activeDevice
        activeDevice.connect()


    def onPTT( self, val ):
        self.tx = not val
        if self.lockSwitch:
            if self.activeDevice:
                self.activeDevice.activateSwitch( self.lockSwitch if self.tx else self.currentSwitch )
        for terminal in self.terminals:
            if self.lockSwitch:
                terminal.updateSwitchLeds( self.lockSwitch if self.tx else self.currentSwitch )
            terminal.activatePTT()

    def onLockButton( self ):
        if not self.tx:
            self.lockSwitch = None if self.lockSwitch else self.currentSwitch
            for terminal in self.terminals:
                terminal.displayLockSwitch()

    def onSwitchButton( self, switch ):
        if not self.tx and self.currentSwitch != switch: 
            self.currentSwitch = switch        
            if self.activeDevice:
                self.activeDevice.activateSwitch( switch )
            for terminal in self.terminals:
                terminal.displayCurrentSwitch()
                terminal.updateSwitchLeds( switch )

class Device:
    def __init__(self, params, cluster):
        self.lines = conf['templates'][params['template']]['lines']
        self.title = params['title']
        self.host = params['host']
        self.cluster = cluster
        self.controller = None
        if params.has_key( 'active' ) and params['active']:
            cluster.setActiveDevice( self )

    def connect( self ):
        self.controller = Controller(  { 'host': self.host, 'UART': False } )
        for line in self.lines:
            self.controller.setLineMode( line, 'out' )
        self.controller.setConnectedCallbacks.append( self.controllerConnected )

    def disconnect( self ):
        if self.controller:
            self.controller.setConnectedCallbacks.remove( self.controllerConnected )
            self.controller.disconnect()
            self.controller = None

    def controllerConnected( self, val ):
        if val:
            self.activateSwitch( self.cluster.lockSwitch if self.cluster.tx and \
                    self.cluster.lockSwitch else self.cluster.currentSwitch )

    def activateSwitch( self, switch ):
        if self.controller.connected and switch:
            for i in range(4):
                self.controller.setLineState( self.lines[i], switch.outLinesStates[ i ] )            




class Terminal:
    class SwitchLine:
        def __init__(self, terminal, lineNo, switch ):
            self.lineState = None
            self.terminal = terminal
            self.lineNo = lineNo
            self.switch = switch
            self.terminal.controller.setCallback( lineNo, self.onLine )

        def onLine( self, val ):
            if self.lineState == None:
                self.lineState = val
                return
            if self.lineState != val:
                self.lineState = val
                if not val:
                    self.terminal.cluster.onSwitchButton( self.switch )




    def __init__( self, params, cluster ):
        self.template = conf['templates'][params['template']]
        self.controller = Controller( { 'host': params['host'], 'UART': True } )
        self.cluster = cluster
        self.lockButtonState = None
        self.pttState = None
        self.switchLeds = {}
        self.switchLines = []
        for switchEntry in self.template['switches']:
            switch = [ x for x in switches if x.combo == tuple(switchEntry['combo']) ][0]
            self.switchLeds[switch] = switchEntry['led']
            self.switchLines.append( Terminal.SwitchLine( self, switchEntry['button'], switch ) )
        self.controller.setLineMode( self.template['lock']['button'], 'in' )
        self.controller.setLineMode( self.template['lock']['led'], 'out' )
        self.controller.setLineMode( self.template['PTT']['line'], 'in' )
        self.controller.setLineMode( self.template['PTT']['led'], 'out' )
        self.controller.setCallback( self.template['lock']['button'], self.onLockButton )
        self.controller.setCallback( self.template['PTT']['line'], self.onPTT )
        self.controller.setConnectedCallbacks.append( self.onControllerConnected )
        self.controller.UARTConnectedCallbacks.append( self.onControllerUARTConnected )

    def onLockButton( self, val ):
        if self.lockButtonState == None:
            self.lockButtonState = val
            return
        if val != self.lockButtonState:
            self.lockButtonState = val
            if not val:
                self.cluster.onLockButton()

    def onPTT( self, val ):
        if self.pttState == None:
            self.pttState = val
            return
        if val != self.pttState:
            self.pttState = val
            self.cluster.onPTT( val )

    def onControllerConnected( self, val ):
        if val:
            self.activatePTT()
            self.updateSwitchLeds( self.cluster.lockSwitch if self.cluster.tx and self.cluster.lockSwitch \
                    else self.cluster.currentSwitch )

    def onControllerUARTConnected( self, val ):
        if val:
            reactor.callLater( 0.1, self.activatePTT )
            reactor.callLater( 0.2, self.displayCurrentSwitch )
            reactor.callLater( 0.3, self.displayLockSwitch )

    def displayLockSwitch( self ):
        if self.controller.connected:
            self.controller.setLineState( self.template['lock']['led'], self.cluster.lockSwitch )
            self.controller.UARTsend( ( ( self.cluster.lockSwitch.UARTsignal if self.cluster.lockSwitch else 0 ) | 8, ) )


    def activatePTT( self ):
        if self.controller.connected:
            self.controller.UARTsend( ( 32 if self.cluster.tx else 16, ) )
            self.controller.setLineState( self.template['PTT']['led'], self.cluster.tx )

    def displayCurrentSwitch( self ):
        if self.controller.connected:
            self.controller.UARTsend( ( self.cluster.currentSwitch.UARTsignal, ) )

    def updateSwitchLeds( self, switch ):
        if self.controller.connected:
            for ( k, v ) in self.switchLeds.iteritems():
                self.controller.setLineState( v, k == switch )

def init():
    global switches
    global clusters
    switches = [ Switch( entry ) for entry in conf['templates']['terminal']['switches'] ]
    clusters = [ Cluster( entry ) for entry in conf['devices'] ]

class WebCluster(Resource):
    isLeaf = True

    def render_GET(self, request):
        cluster = clusters[ int( request.args['cluster'][0] ) ]

#        stateIN = controller['controller'].getLineState(controller['lineIN'])
#        r = [ line + 1 for line in range( len( controller['lines'] ) )
#                if controller['controller'].getLineState( controller['lines'][line] ) == stateIN ]
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps( { 'activeController': cluster.devices.index( cluster.activeDevice ), \
                'activeCombo': cluster.currentSwitch.combo if cluster.currentSwitch else None, \
                'lockCombo': cluster.lockSwitch.combo if cluster.lockSwitch else None } )

    def render_POST(self, request):
        params = json.loads( request.content.getvalue() )
        cluster = clusters[ int( params['cluster'] ) ]
        if params.has_key( 'controller' ):
            newDev = cluster.devices[ int( params['controller'] ) ]
            if cluster.activeDevice != newDev:
                cluster.setActiveDevice( newDev )
        if params.has_key( 'combo' ):
            combo = tuple( params['combo'] )
            switch = [ x for x in switches if x.combo == combo ][0]
            cluster.onSwitchButton( switch )
        return "OK"

class WebData(Resource):
    isLeaf = True

    def render_GET( self, request ):
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps( conf['devices'] )

siteRoot = static.File( appPath + '\web' )
siteRoot.putChild( 'cluster', WebCluster() )
siteRoot.putChild( 'data', WebData() )
init()

site = Site( siteRoot )
reactor.listenTCP( conf['http_port'], site)
reactor.run()

