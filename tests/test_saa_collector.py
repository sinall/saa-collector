from saa_collector.main import SaaCollectorTest


def test_saa_collector():
    # test saa_collector without any subcommands or arguments
    with SaaCollectorTest() as app:
        app.run()
        assert app.exit_code == 0


def test_saa_collector_debug():
    # test that debug mode is functional
    argv = ['--debug']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        assert app.debug is True


def test_command1():
    # test command1 without arguments
    argv = ['command1']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['foo'] == 'bar'
        assert output.find('Foo => bar')


def test_collect_stocks():
    argv = ['collect-stocks', '-s', '000001']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['symbol'] == '000001'
        assert output.find('Symbol => 000001')
