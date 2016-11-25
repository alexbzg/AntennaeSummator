var antSummApp = angular.module( "antSummApp", [], function($rootScopeProvider) {
  $rootScopeProvider.digestTtl(20);
});

antSummApp.controller( 'antSummCtrl', function( $scope, $http ) {

    $scope.controller = null;
    $scope.activeCombo = null;
    $scope.lock = false;

    $scope.range = function(min, max, step){
        step = step || 1;
        var input = [];
        for (var i = min; i <= max; i += step) input.push(i);
        return input;
    };

    function combos( n, m ) {
        var r = [];
        for ( var i = 1; i <= m - n + 1; i++ ) {
            if ( n > 1 ) {
                var combos1 = combos( n - 1, m - i );
                var combos1Length = combos1.length;
                for ( var c0 = 0; c0 < combos1Length; c0++ ) {
                    var combo = { lines: [ i ], title: i + "" };
                    for (var c1 = 0; c1 < n - 1; c1++ ) {
                        ni = i + combos1[ c0 ].lines[ c1 ];
                        combo.lines.push( ni );
                        combo.title += " + " + ni;
                    }
                    r.push( combo );
                } 
            } else 
                r.push( { lines: [i], title: i + "" } );
        }
        return r;
    }

    $scope.setActiveCluster = function( cluster ) {
        $scope.activeCluster = cluster;
        $http.get( '/cluster?cluster=' + $scope.clusters.indexOf( cluster ) ).then(
            function( response ) {
                cluster.activeCombo = response.data.activeCombo;
                cluster.activeController = cluster.controllers[ response.data.activeController ];
            } );
    };

    $scope.setActiveController = function( idx ) {
        $http.post( '/cluster' ,
                { cluster:  $scope.clusters.indexOf( $scope.activeCluster ),
                    controller: idx } )
        .then( function( response ) {
            $scope.activeCluster.activeController =
                $scope.activeCluster.controllers[idx];
        });
    };

    $scope.setActiveCombo = function( combo ) {
        if (  $scope.controller.activeCombo == null ||
                $scope.controller.activeCombo.title != 
                combo.title ) {
            $scope.controller.activeCombo = combo;
            $http.post( '/controller', 
                    { controller: $scope.controller.id,
                        lines: combo.lines } );
        }
    };

    $http.get( '/data' ).then( function( response ) {
        $scope.clusters = response.data;
        $scope.clusters.forEach( function( item ) {
            item.combos = {};
            item.lines = 3;
            item.no = 
            item.activeCombo = null;
            item.activeController = null;
            for ( var n = 1; n <= item.lines; n++ )
                item.combos[ n ] = combos( n, item.lines );            
        });
    } ) } );
