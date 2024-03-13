#!/usr/bin/env python3
"""GHSCI graphical user interface; run and access at https://localhost:8080."""


import os.path

import pandas as pd
from configure import configuration
from nicegui import Client, app, run, ui
from subprocesses import ghsci
from subprocesses.leaflet import leaflet
from subprocesses.local_file_picker import local_file_picker

ticks = ['✘', '✔']
# default_location = [14.509097, 154.832401]
default_location = [10, 154.8]
default_zoom = 2

regions = {}
region_list = []


def get_region(codename) -> dict:
    # initialise region
    region = {
        'id': len(regions) + 1,
        'codename': codename,
        'config': None,
        'name': '',
        'study_region': ('Select or create a new study region',),
        'configured': ticks[False],
        'analysed': ticks[False],
        'generated': ticks[False],
        'geojson': None,
    }
    # load region
    try:
        # print(codename)
        r = ghsci.Region(codename)
        if r is None or r.config['data_check_failures'] is not None:
            region[
                'study_region'
            ] = f'{codename} (configuration not yet complete)'
            # print(
            # '- study region configuration file could not be loaded and requires completion in a text editor.',
            # )
        else:
            region[
                'study_region'
            ] = f"{r.name}, {r.config['country']}, {r.config['year']}"
            region['config'] = r.config
            region['configured'] = ticks[True]
            if 'urban_study_region' in r.tables:
                if {'indicators_region', r.config['grid_summary']}.issubset(
                    r.tables,
                ):
                    region['analysed'] = ticks[True]
                    region['generated'] = ticks[
                        os.path.isfile(
                            f'{r.config["region_dir"]}/{r.codename}_indicators_region.csv',
                        )
                    ]
                    region['geojson'] = r.get_geojson(
                        'urban_study_region', include_columns=['db'],
                    )
    except Exception as e:
        region['study_region'] = f'{codename} (configuration not yet complete)'
        # print(
        # '- study region configuration file could not be loaded and requires completion in a text editor.',
        # )
    finally:
        regions[codename] = region


async def get_regions(map):
    global regions
    regions = {}
    global region_list
    region_list = []
    for codename in ghsci.region_names:
        get_region(codename)
        region_list.append(
            {
                'id': regions[codename]['id'],
                'codename': regions[codename]['codename'],
                'name': regions[codename]['name'],
                'study_region': regions[codename]['study_region'],
                'configured': regions[codename]['configured'],
                'analysed': regions[codename]['analysed'],
                'generated': regions[codename]['generated'],
            },
        )
    return regions
    # if regions[codename]['geojson'] is not None:
    # map.add_geojson(regions[codename]['geojson'], remove=False)


def set_region(map, selection) -> None:
    global region
    if regions is not None:
        region = regions[selection['codename']]
        # print(region)
        if region['configured'] == ticks[True]:
            if region['geojson'] is not None:
                try:
                    map.add_geojson(region['geojson'])
                except Exception as e:
                    map.set_no_location(default_location, default_zoom)
            else:
                map.set_no_location(default_location, default_zoom)
        else:
            map.set_no_location(default_location, default_zoom)


def try_function(
    function,
    args=[],
    fail_message='Function failed to run; please check configuration and the preceding analysis steps have been performed successfully.',
):
    try:
        result = function(*args)
    except Exception as e:
        ui.notify(f'{fail_message}: {e}')
        result = None
    finally:
        return result


def summary_table():
    if region['study_region'] == ('Select or create a new study region',):
        with ui.dialog() as dialog, ui.card():
            ui.label(
                "Select a study region from the list in the table below; these correspond to configuration files located in the folder 'process/configuration/regions'.  You can also initialise a new study region configuration via the 'Add a new codename' field. Once configuration is complete, analysis can be run.  Following analysis, summary indicator results can be viewed by clicking the city name heading and PDF analysis and indicator reports may be generated and comparison analyses run.",
            )
            ui.button('Close', on_click=dialog.close)
        dialog.open()
        return None
    else:
        region['summary'] = ghsci.Region(region['codename']).get_df(
            'indicators_region', exclude='geom',
        )
        if region['summary'] is None:
            with ui.dialog() as dialog, ui.card():
                status = ['Configuration', 'Analysis'][
                    region['configured'] == ticks[True]
                ]
                hints = [
                    'Hints for next steps may be displayed in the command line interface used to launch the app. ',
                    '',
                ][region['configured'] == ticks[True]]
                ui.label(
                    f'{status} does not appear to have been completed for the selected city. {hints}Once configuration is complete, analysis can be run.  Following analysis, summary indicator results can be viewed by clicking the city name heading and PDF analysis and indicator reports may be generated and comparison analyses run.',
                )
                ui.button('Close', on_click=dialog.close)
            dialog.open()
            return None
        region['summary'] = region['summary'].transpose().dropna()
        row_key = region['summary'].index.name
        region['summary'].index = region['summary'].index.map(
            ghsci.dictionary['Description'].to_dict(), na_action='ignore',
        )
        region['summary'] = region['summary'].reset_index()
        values = region['summary'].to_dict('records')
        values = [
            {
                k: float(f'{v:.1f}') if isinstance(v, float) else v
                for k, v in x.items()
            }
            for x in values
        ]
        if region['summary'] is not None:
            with ui.dialog() as dialog, ui.card():
                table = ui.table(
                    columns=[
                        {
                            'name': col,
                            'label': '',
                            'field': col,
                            'style': 'white-space: normal;',
                        }
                        for col in region['summary'].columns
                    ],
                    rows=values,
                    row_key=row_key,
                ).style('white-space: normal;')
                with table.add_slot('top-left'):

                    def toggle() -> None:
                        table.toggle_fullscreen()
                        button.props(
                            'icon=fullscreen_exit'
                            if table.is_fullscreen
                            else 'icon=fullscreen',
                        )

                    button = ui.button(
                        'Toggle fullscreen',
                        icon='fullscreen',
                        on_click=toggle,
                    ).props('flat')
                dialog.open()


def comparison_table(comparison, comparison_list=None):
    if region['codename'] is None:
        ui.notify(
            "Please select a reference region having completed analysis from the table in the 'Study Regions' tab before proceeding.",
        )
        return
    elif region['codename'] not in comparison_list:
        ui.notify(
            f"Please confirm that analysis has been completed for {region['codename']} before proceeding.",
        )
        return
    elif comparison == region['codename']:
        ui.notify(
            f'Selected region and comparison region are the same ({comparison}).  Please select a different study region to compare.',
        )
        return
    else:
        comparison = try_function(
            ghsci.Region(region['codename']).compare, [comparison],
        )
        if comparison is None:
            ui.notify(
                "Check that the reference and comparison study regions have been selected and analysed before proceeding (current selection didn't work!)",
            )
            return None
        comparison.index = comparison.index.map(
            ghsci.dictionary['Description'].to_dict(), na_action='ignore',
        ).set_names('Indicators')
        comparison = comparison.reset_index()
        values = comparison.to_dict('records')
        values = [
            {
                k: float(f'{v:.1f}') if isinstance(v, float) else v
                for k, v in x.items()
            }
            for x in values
        ]
        if comparison is not None:
            with ui.dialog() as dialog, ui.card().style('min-width:90%'):
                table = ui.table(
                    columns=[
                        {
                            'name': col,
                            'label': col,
                            'field': col,
                            'style': 'white-space: normal;',
                        }
                        for col in comparison.columns
                    ],
                    rows=values,
                    row_key='Indicators',
                ).style('white-space: normal;')
                with table.add_slot('top-left'):

                    def toggle() -> None:
                        table.toggle_fullscreen()
                        button.props(
                            'icon=fullscreen_exit'
                            if table.is_fullscreen
                            else 'icon=fullscreen',
                        )

                    button = ui.button(
                        'Toggle fullscreen',
                        icon='fullscreen',
                        on_click=toggle,
                    ).props('flat')
                dialog.open()


def add_location_row(codename: str, regions) -> dict:
    location_row = {
        'id': len(regions) + 1,
        'codename': codename,
        'name': '',
        'study_region': 'Select or create a new study region',
        'configured': ticks[False],
        'analysed': ticks[False],
        'generated': ticks[False],
        'geojson': None,
    }
    # regions[codename] = location_row.copy()
    return location_row


def setup_ag_columns() -> dict:
    not_included_columns = ['id', 'centroid', 'zoom', 'geojson']
    not_editable_columns = ['configured', 'analysed', 'generated']
    columns = ['codename', 'study_region'] + not_editable_columns
    ag_columns = []
    for c in columns:
        ag_columns.append(
            {'headerName': c.capitalize(), 'field': c, 'tooltipField': c},
        )
    ag_columns[0]['sort'] = 'asc'
    ag_columns[0]['width'] = 190
    ag_columns[1]['width'] = 190
    return ag_columns


ag_columns = setup_ag_columns()


# @ui.refreshable
def region_ui(map) -> None:
    async def output_selected_row():
        global selection
        selection = await grid.get_selected_row()
        if selection:
            set_region(map, selection)
            studyregion_ui.refresh()
            show_carousel.refresh()

    def add_new_codename(new_codename, regions) -> None:
        """Add a new codename to the list of study regions."""
        if (
            new_codename.value.strip() != ''
            and new_codename.value not in ghsci.region_names
        ):
            configuration(new_codename.value)
            new_row = add_location_row(new_codename.value, regions)
            regions.append(new_row)
            new_codename.set_value(None)
            grid.update()

    with ui.row():
        with ui.input('Add new codename').style('width: 25%').on(
            'keydown.enter',
            lambda e: (add_new_codename(new_codename, regions),),
        ) as new_codename:
            ui.tooltip(
                'For example, "AU_Melbourne_2023" is a codename for the city of Melbourne, Australia in 2023',
            ).style('color: white;background-color: #6e93d6;')
        with ui.input(
            'Search configured regions',
            on_change=lambda e: grid.call_api_method(
                'setQuickFilter', filter_text.value,
            ),
        ).props('clearable').style('width: 70%') as filter_text:
            ui.tooltip(
                'Enter text to filter the list of configured regions.',
            ).style('color: white;background-color: #6e93d6;')
    grid = ui.aggrid(
        {
            'columnDefs': ag_columns,
            'defaultColDef': {
                # 'flex': 1,
                'width': 95,
                'sortable': True,
            },
            'rowData': region_list,
            'rowSelection': 'single',
            'accentedSort': True,
            # 'cacheQuickFilter': True,
        },
        theme='material',
    ).on('click', output_selected_row)
    with ui.row():
        ui.label().bind_text_from(region, 'notes').style('font-style: italic;')


def format_policy_checklist(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    df = pd.read_excel(xlsx, sheet_name='Policy Checklist', header=1)
    df.columns = [
        'Indicators',
        'Measures',
        'Principles',
        'Policy',
        'Level of government',
        'Adoption date',
        'Citation',
        'Text',
        'Mandatory',
        'Measurable target',
        'Measurable target text',
        'Evidence-informed threshold',
        'Threshold explanation',
        'Notes',
    ]
    # Exclude dataframe rows where an indicator is defined without a corresponding measure
    # These are short name headings, and this is the quickest way to get rid of them!
    df = df.query('~(Indicators == Indicators and Measures != Measures)')
    # fill down Indicators column values
    df.loc[:, 'Indicators'] = df.loc[:, 'Indicators'].ffill()
    # fill down Measures column values
    df.loc[:, 'Measures'] = df.loc[:, 'Measures'].ffill()
    df = df.loc[~df['Indicators'].isna()]
    df = df.loc[df['Indicators'] != 'Indicators']
    df['qualifier'] = (
        df['Principles']
        .apply(
            lambda x: x
            if (x == 'No' or x == 'Yes' or x == 'Yes, explicit mention of:')
            else pd.NA,
        )
        .ffill()
        .fillna('')
    )
    # replace df['qualifier'] with '' where df['Principles'] is in ['Yes','No'] (i.e. where df['Principles'] is a qualifier)
    df = df.loc[
        ~df['Principles'].isin(['No', 'Yes', 'Yes, explicit mention of:'])
    ]
    df.loc[:, 'Principles'] = df.apply(
        lambda x: x['Principles']
        if x['qualifier'] == ''
        else f"{x['qualifier']}: {x['Principles']}".replace('::', ':'),
        axis=1,
    )
    df.drop(columns=['qualifier'], inplace=True)
    sections = {
        'CITY PLANNING REQUIREMENTS': {
            'indicators': {
                'Integrated transport and urban planning': 'Integrated transport and urban planning actions to create healthy and sustainable cities',
                'Air pollution': 'Limit air pollution from land use and transport',
                'Transport infrastructure investment by mode': 'Priority investment in public and active transport',
                'Disaster mitigation': 'City planning contributes to adaptation and mitigating  the effects of climate change',
            },
        },
        'WALKABILITY POLICIES': {
            'indicators': {
                'Density': 'Appropriate context-specific housing densities that encourage walking; including higher density development around activity centres and transport hubs',
                'Demand management': 'Limit car parking and price parking appropriately for context',
                'Diversity': 'Diverse mix of housing types and local destinations needed for daily living',
                'Destination proximity': ' Local destinations for walkable cities',
                'Desirability': 'Crime prevention through urban design principles, manage traffic exposure, and establish urban greening provisions',
                'Design': 'Create pedestrian- and cycling-friendly neighbourhoods, requiring highly connected street networks; pedestrian and cycling infrastructure provision; and public open space',
            },
        },
        'PUBLIC TRANSPORT POLICIES': {
            'indicators': {
                'Destination accessibility': 'Coordinated planning for transport, employment and infrastructure that ensures access by public transport',
                'Distribution of employment': 'A balanced ratio of jobs to housing ',
                'Distance to public transport': 'Nearby, walkable access to public transport',
            },
        },
    }
    indicator_measures = {
        'Integrated transport and urban planning actions to create healthy and sustainable cities': [
            'Transport and planning combined in one government department',
            'Explicit health-focused actions in urban policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Explicit health-focused actions in transport policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Health Impact Assessment requirements incorporated into urban/transport policy or legislation',
            'Urban and/or transport policy explicitly aims for integrated city planning',
        ],
        'Limit air pollution from land use and transport': [
            'Transport policies to limit air pollution',
            'Land use policies to reduce air pollution exposure',
        ],
        'Priority investment in public and active transport': [
            'Information on government expenditure on infrastructure for different transport modes',
        ],
        'City planning contributes to adaptation and mitigating  the effects of climate change': [
            'Adaptation and disaster risk reduction strategies',
        ],
        'Appropriate context-specific housing densities that encourage walking; including higher density development around activity centres and transport hubs': [
            'Housing density requirements citywide or within close proximity to transport or town centres',
            'Height restrictions on residential buildings (min and/or max)',
            'Required urban growth boundary or maximum levels of greenfield housing development',
        ],
        'Limit car parking and price parking appropriately for context': [
            'Parking restrictions to discourage car use',
        ],
        'Diverse mix of housing types and local destinations needed for daily living': [
            'Mixture of local destinations for daily living ',
            'Mixture of housing types and sizes',
        ],
        'Local destinations for healthy, walkable cities': [
            'Requirements for distance to daily living destinations',
            'Requirements for healthy food environments',
        ],
        'Crime prevention through urban design principles, manage traffic exposure, and establish urban greening provisions': [
            'Tree canopy and urban greening requirements',
            'Urban biodiversity protection & promotion',
            'Traffic safety requirements',
            'Crime prevention through environmental design requirements',
        ],
        'Create pedestrian- and cycling-friendly neighbourhoods, requiring highly connected street networks; pedestrian and cycling infrastructure provision; and public open space': [
            'Street connectivity requirements',
            'Pedestrian infrastructure provision requirements',
            'Cycling infrastructure provision requirements',
            'Walking participation targets',
            'Cycling participation targets',
            'Minimum requirements for public open space access',
        ],
        'Coordinated planning for transport, employment and infrastructure that ensures access by public transport': [
            'Requirements for public transport access to employment and services',
        ],
        'A balanced ratio of jobs to housing ': [
            'Employment distribution requirements',
            'Requirements for ratio of jobs to housing',
        ],
        'Nearby, walkable access to public transport': [
            'Minimum requirements for public transport access',
            'Targets for public transport use ',
        ],
    }
    for section in sections:
        for indicator in sections[section]['indicators']:
            # clean up Measures column values (remove 'see also' references, remove leading and trailing spaces, replace '&nbsp' with ' ', replace '  ' with ' ')
            df.loc[
                df.loc[:, 'Indicators']
                == sections[section]['indicators'][indicator],
                'Measures',
            ] = (
                df.loc[
                    df.loc[:, 'Indicators']
                    == sections[section]['indicators'][indicator]
                ]
                .apply(
                    lambda x: x.str.strip()
                    .replace('&nbsp', ' ')
                    .replace('  ', '')
                    if x['Measures'] in indicator_measures[x['Indicators']]
                    else pd.NA,
                    axis=1,
                )['Measures']
                .ffill()
            )
            # concatenate section and short form of indicator name
            df.loc[
                df.loc[:, 'Indicators']
                == sections[section]['indicators'][indicator],
                'Indicators',
            ] = f'{section} - {indicator}'
    return df


@ui.refreshable
def studyregion_ui() -> None:
    ui.button(
        region['study_region'], on_click=summary_table, color='#6e93d6',
    ).props('icon=info').style('color: white')


ghsci.datasets.pop('dictionary', None)


columns = []
for c in [
    'codename',
    'configured',
    'analysed',
    'generated',
]:
    columns.append(
        {
            'name': c,
            'label': c.capitalize(),
            'field': c,
            'sortable': True,
            'required': True,
        },
    )


async def load_policy_checklist() -> None:
    from policy_report import PDF_Policy_Report

    xlsx = await local_file_picker('/home/ghsci/process/data', multiple=True)
    if xlsx is not None:
        try:
            df = format_policy_checklist(xlsx[0])
        except Exception as e:
            ui.notify(
                f'Policy checklist could not be loaded; please check the file is in the correct format and try again. Specific error: {e}',
            )
            return None
        policy_columns = []
        for c in df.columns:
            policy_columns.append(
                {
                    'name': c,
                    'label': c.capitalize().strip(),
                    'field': c,
                    'sortable': True,
                    'required': True,
                    'width': 100,
                    'wrap-cells': True,
                },
            )
        with ui.dialog() as dialog, ui.card().style('min-width: 1800px'):
            with ui.table(
                columns=policy_columns, rows=df.to_dict('records'),
            ).classes('w-full').props(
                'wrap-cells=true table-style="{vertical-align: text-top}"',
            ) as table:
                with table.add_slot('top-left'):
                    ui.button(
                        'Generate PDF',
                        on_click=lambda: (
                            ui.notify(
                                PDF_Policy_Report(
                                    xlsx[0],
                                ).generate_policy_report(),
                            )
                        ),
                    ).props('icon=download_for_offline outline').classes(
                        'shadow-lg',
                    ).tooltip(
                        f"Save an indexed PDF of the policy checklist to {xlsx[0].replace('.xlsx','.pdf')}.  Please wait a few moments for this to be generated after clicking.",
                    ).style(
                        'color: white;background-color: #6e93d6;',
                    )
                with table.add_slot('top-right'):
                    with ui.input(placeholder='Search').props(
                        'type=search',
                    ).bind_value(table, 'filter').add_slot('append'):
                        ui.icon('search').tooltip(
                            'Search for key words',
                        ).style('color: white;background-color: #6e93d6;')
            dialog.open()


def ui_exit():
    with ui.dialog() as dialog, ui.card():
        ui.label('Exiting user interface; please close this window.')
        dialog.open()
        app.shutdown()


def reset_region():
    global region
    region = {
        'id': None,
        'codename': None,
        'config': None,
        'name': '',
        'study_region': ('Select or create a new study region',),
        'configured': ticks[False],
        'analysed': ticks[False],
        'generated': ticks[False],
        'geojson': None,
    }


@ui.refreshable
def show_carousel():
    # create a list of images in the region output figures folder
    if (
        region['configured'] == ticks[True]
        and region['analysed'] == ticks[True]
    ):
        ui.label(
            'Click the button below to generate project documentation and resources (data, images, maps, reports, etc).  More information on the outputs is displayedin the terminal window.',
        )
        images = []
        if (
            region['config'] is not None
            and 'region_dir' in region['config']
            and os.path.isdir(f'{region["config"]["region_dir"]}/figures')
        ):
            images = [
                f'{region["config"]["region_dir"]}/figures/{x}'
                for x in os.listdir(
                    f'{region["config"]["region_dir"]}/figures',
                )
                if x.endswith('.png') or x.endswith('.jpg')
            ]
        if len(images) > 0:
            with ui.row():
                # add nicegui button to 'View Resources'
                ui.button(
                    'Re-generate resources',
                    on_click=lambda: (
                        try_function(
                            ghsci.Region(region['codename']).generate,
                        ),
                        show_carousel.refresh(),
                    ),
                )
                ui.separator()
                ui.button(
                    'View generated images',
                    on_click=lambda: view_resources(images),
                    color='#6e93d6',
                ).props('icon=perm_media').style('color: white')
        else:
            ui.button(
                'Generate resources',
                on_click=lambda: (
                    try_function(ghsci.Region(region['codename']).generate),
                    show_carousel.refresh(),
                ),
            )
    else:
        ui.label(
            'Select a configured study region for which analysis has been completed to generate and/or view resources.',
        )


def view_resources(images):
    with ui.dialog() as dialog, ui.card().style(
        'min-width:800px; min-height: 700px',
    ):
        # add nicegui carousel
        with ui.carousel(arrows=True, navigation=False).props(
            # 'thumbnails=True,autoplay="1000"'
            'thumbnails=True',
        ).classes('bg-grey-9 shadow-2 rounded-borders').style(
            'min-width:700px; height:700px; display: block; margin-left: auto; margin-right: auto; control-color: #6e93d6',
        ):
            for image in images:
                with ui.carousel_slide().style('height:700px; width:700px;'):
                    ui.image(image).props('width=600px').style(
                        'display: block; margin-left: auto; margin-right: auto;background: #FFFFFF',
                    )
                    ui.label(os.path.basename(image)).style(
                        'text-align: center; font-size: 150%; font-weight: 300; color: #FFFFFF;',
                    )
        ui.button('Close', on_click=dialog.close)
    dialog.open()


@ui.page('/')
async def main_page(client: Client):
    # Begin layout
    reset_region()
    ## Title
    with ui.column().props('style="max-width: 1020px"'):
        ui.label('Global Healthy and Sustainable City Indicators').style(
            'color: #6E93D6; font-size: 200%; font-weight: 300',
        )
        ui.button().props('icon=logout outline round ').classes(
            'shadow-lg',
        ).style('position: absolute; right: 20px;').on(
            'click', ui_exit,
        ).tooltip(
            'Exit',
        )
        ui.markdown(
            'Open-source software for calculating and reporting on policy and spatial indicators for healthy, sustainable cities worldwide using open or custom data. This tool has been created to support the 1000 Cities Challenge of the [Global Observatory of Healthy and Sustinable Cities](https://healthysustainablecities.org).',
        ).style(
            'font-familar:Roboto,-apple-system,Helvetica Neue,Helvetica,Arial,sans-serif; color: #6E93D6;',
        )
    with ui.card().tight().style('width:1010px;') as card:
        studyregion_ui()
        ## Body
        map = leaflet().style('width:100%;height:30rem')
        map.set_no_location(default_location, default_zoom)
        regions = await get_regions(map)
        with ui.tabs().props('align="left"').style('width:100%') as tabs:
            with ui.tab('Study regions', icon='language'):
                ui.tooltip('Select or create a new study region').style(
                    'color: white;background-color: #6e93d6;',
                )
            ui.tab('Configure', icon='build')
            ui.tab('Analysis', icon='data_thresholding')
            ui.tab('Generate', icon='perm_media')
            ui.tab('Compare', icon='balance')
            ui.tab('Policy checklist', icon='check_circle')
        with ui.tab_panels(tabs, value='Study regions').style('width:100%'):
            with ui.tab_panel('Study regions'):
                region_ui(map)
            with ui.tab_panel('Configure'):
                ui.markdown(
                    'Study region, shared dataset and project details can be set up and modified by editing the .yml text files located in the process/configuration folder in a text editor, as per the directions at [https://global-healthy-liveable-cities.github.io/](https://global-healthy-liveable-cities.github.io/).  Study region settings are defined in the .yml files located in configuration/regions corresponding to the codenames defined above.  Define shared datasets for use in your project using configuration/datasets.yml. Project settings can be edited using configuration/config.yml.  Additional reporting languages can be configured using the Excel spreadsheet configuration/reportconfiguration.xlsx',
                )
            with ui.tab_panel('Analysis'):
                ui.label(
                    'Click the button below to run the analysis workflow.  Progress can be monitored from your terminal window, however this user interface may not respond until processing is complete.',
                )
                ui.button(
                    'Perform study region analysis',
                    on_click=lambda: (
                        try_function(
                            ghsci.Region(region['codename']).analysis,
                        ),
                        # set_region(map, selection)
                    ),
                )
            with ui.tab_panel('Generate'):
                show_carousel(),
            with ui.tab_panel('Compare'):
                ui.label(
                    'To compare the selected region with another comparison region with generated resources (eg. as a sensitivity analysis, a benchmark comparison, or evaluation of an intervention or scenario), select a comparison using the drop down menu:',
                )
                if regions is not None:
                    comparison_list = [
                        regions[r]['codename']
                        for r in regions
                        if regions[r]['generated'] == ticks[True]
                    ]
                    comparison = ui.select(
                        comparison_list,
                        with_input=True,
                        value='Select comparison study region codename',
                    ).style('width:60%')
                    ui.button(
                        'Compare study regions',
                        on_click=lambda: (
                            comparison_table(
                                comparison.value, comparison_list,
                            )
                        ),
                    )
            with ui.tab_panel('Policy checklist'):
                ui.label(
                    'Upload a completed policy checklist to explore and link with analysis results.',
                )
                ui.button('Choose file', on_click=load_policy_checklist).props(
                    'icon=folder',
                )


# NOTE on windows reload must be disabled to make asyncio.create_subprocess_exec work (see https://github.com/zauberzeug/nicegui/issues/486)
ui.run(
    # reload=platform.system() != 'Windows',
    reload=False,
    title='GHSCI',
    show=False,
    favicon=r'configuration/assets/favicon.ico',
)
