from src.reference_discovery import build_discovery_requests, ingest_results, source_type_for


def config():
    return {
        'sources':{
            'manufacturer':{'requires_manual_approval':False},
            'review_site':{'requires_manual_approval':False},
            'ebay':{'requires_manual_approval':True},
        },
        'discovery':{
            'maximum_results_per_query':5,
            'minimum_model_token_ratio':0.60,
            'source_domains':{
                'manufacturer':['asus.com'],
                'review_site':['anandtech.com'],
            },
            'marketplace_domains':['ebay.com'],
        },
    }


def test_domain_classification_supports_subdomains():
    assert source_type_for('https://rog.asus.com/boards/model',config())=='manufacturer'
    assert source_type_for('https://www.anandtech.com/show/1',config())=='review_site'
    assert source_type_for('https://www.ebay.com/itm/1',config())=='ebay'
    assert source_type_for('https://unknown.example/board',config()) is None


def test_plan_expands_gap_queries():
    queue=[{'item_id':'1','model':'ASUS P8P67 EVO','search_queries':['query one','query two']}]
    requests=build_discovery_requests(queue,config())
    assert len(requests)==2
    assert requests[0]['maximum_results']==5


def test_ingest_filters_domains_and_model_mismatches():
    queue=[{'item_id':'1','model':'ASUS P8P67 EVO'}]
    results=[
        {'item_id':'1','title':'ASUS P8P67 EVO motherboard','page_url':'https://www.asus.com/p8p67-evo','image_url':'https://www.asus.com/p8p67-evo.jpg'},
        {'item_id':'1','title':'ASUS Z690 motherboard','page_url':'https://www.asus.com/z690','image_url':'https://www.asus.com/z690.jpg'},
        {'item_id':'1','title':'ASUS P8P67 EVO','page_url':'https://spam.example/p8p67','image_url':'https://spam.example/p8p67.jpg'},
    ]
    accepted,rejected=ingest_results(queue,results,config())
    assert len(accepted)==1
    assert accepted[0]['source_type']=='manufacturer'
    assert {row['rejection_reason'] for row in rejected}=={'insufficient_model_evidence','unapproved_domain'}


def test_marketplace_result_remains_manual():
    queue=[{'item_id':'1','model':'ASUS P8P67 EVO'}]
    results=[{'item_id':'1','title':'ASUS P8P67 EVO','page_url':'https://www.ebay.com/itm/1','image_url':'https://i.ebayimg.com/p8p67-evo.jpg'}]
    accepted,_=ingest_results(queue,results,config())
    assert accepted[0]['requires_manual_approval'] is True
