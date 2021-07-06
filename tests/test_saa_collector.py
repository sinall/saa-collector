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


def test_produce_all_statements():
    argv = ['produce-all-statements', '-s', '000001', '--start-date', '2018-09-22']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['symbol'] == '000001'
        assert output.find('Symbol => 000001')


def test_collect_all_statements():
    argv = ['collect-all-statements', '-s', '000001']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['symbol'] == '000001'
        assert output.find('Symbol => 000001')


def test_collect_capital():
    argv = ['collect-capital', '-s', '000001']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['symbol'] == '000001'
        assert output.find('Symbol => 000001')


def test_collect_main_business():
    argv = ['collect-main-business', '-s', '000001']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['symbol'] == '000001'
        assert output.find('Symbol => 000001')


def test_collect_historical_price():
    argv = ['collect-historical-price', '-d', '2020-02-28']
    with SaaCollectorTest(argv=argv) as app:
        app.run()
        data, output = app.last_rendered
        assert data['symbol'] == '000001'
        assert output.find('Symbol => None')
