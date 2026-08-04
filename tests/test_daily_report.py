from src.daily_report import build_report, render_html


def test_report_selects_bid_candidates_and_alerts():
    values = [{'item_id':'1','title':'Board','recommendation':'bid','expected_profit':100,'confidence':0.9,'recommended_max_bid':80,'current_bid':20}]
    run = {'status':'completed','listings_found':1,'processed':1,'search_errors':[],'gallery_errors':[],'image_download_errors':[]}
    health = {'healthy':True,'reasons':[]}
    config = {'report':{'top_bid_candidates':20,'top_review_candidates':20},'alerts':{'minimum_expected_profit':75,'minimum_confidence':0.75,'maximum_recommended_bid':300,'include_drift':True,'include_crawler_failures':True}}
    report = build_report(values, run, health, config)
    assert report['summary']['bid_candidates'] == 1
    assert report['alerts'][0]['type'] == 'bid_candidate'
    assert '<html>' in render_html(report)
