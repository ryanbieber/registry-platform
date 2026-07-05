import io
import zipfile
from uuid import uuid4

import anyio
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select
from openpyxl import Workbook

from registry.models import Alias, Address, IngestionCheckpoint, IngestionRun, Offense, Photo, Registrant, SourceRecord
from registry.services import ingest_source
from registry.sources.base import SourceConnector
from registry.sources.persistence import persist_normalized_records
from registry.sources.states.florida import FloridaRegistryCsvConnector
from registry.sources.states.iowa import IowaRegistryApiConnector
from registry.sources.states.michigan import MichiganRegistryConnector
from registry.sources.states.minnesota import MinnesotaRegistryConnector
from registry.sources.states.nebraska import NebraskaRegistryConnector
from registry.sources.states.missouri import MissouriRegistryConnector
from registry.sources.states.north_dakota import NorthDakotaRegistryConnector, _parse_search_results
from registry.sources.states.north_carolina import NorthCarolinaRegistryConnector
from registry.sources.states.south_dakota import SouthDakotaRegistryConnector
from registry.sources.states.texas import TexasRegistryConnector
from registry.sources.states.wisconsin import WisconsinRegistryConnector, _SearchTooBroad


def _fixed_width_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = []
    for index, header in enumerate(headers):
        value_lengths = [len(str(row[index])) for row in rows if index < len(row)]
        widths.append(max([len(header), *value_lengths], default=len(header)) + 2)

    def render_row(values: list[str]) -> str:
        cells = []
        for index, width in enumerate(widths):
            cell = str(values[index]) if index < len(values) else ""
            cells.append(cell.ljust(width))
        return " ".join(cells).rstrip()

    header_line = render_row(headers)
    separator_line = " ".join("-" * width for width in widths)
    body = "\n".join(render_row(row) for row in rows)
    return "\n".join([header_line, separator_line, body, ""])


def _make_north_carolina_zip_bytes() -> bytes:
    files = {
        "Public Individual Information.txt": _fixed_width_table(
            [
                "SexRegistrationNumber",
                "FullName",
                "Race",
                "Sex",
                "Height",
                "Weight",
                "EyeColor",
                "HairColor",
                "DepartmentofCorrectionNumber",
                "RegistrationType",
                "PublicRegistrationTypeDescription",
                "PendingSourceCode",
                "PendingSourceCodeDescription",
                "RegistrationDate",
                "AddressLine1",
                "AddressLine2",
                "City",
                "State",
                "Zip",
                "CountyName",
                "PrimaryBirthDate",
            ],
            [
                [
                    "0000001A",
                    "DOE,JOHN A",
                    "White",
                    "Male",
                    "180",
                    "210",
                    "Brown",
                    "Black",
                    "DC12345",
                    "R1",
                    "Registration Type",
                    "P1",
                    "Pending Source",
                    "2024-01-15",
                    "123 Main St",
                    "",
                    "Raleigh",
                    "NC",
                    "27601",
                    "Wake",
                    "1980-02-03",
                ]
            ],
        ),
        "Public Name Information.txt": _fixed_width_table(
            ["SexRegistrationNumber", "FullName"],
            [["0000001A", "JOHN A DOE"]],
        ),
        "Public Address Information.txt": _fixed_width_table(
            ["SexRegistrationNumber", "AddressDate", "VerifyDate", "City", "State", "Zip", "CountyName"],
            [["0000001A", "2024-01-15", "2024-02-01", "Raleigh", "NC", "27601", "Wake"]],
        ),
        "Public Offense Information.txt": _fixed_width_table(
            [
                "SexRegistrationNumber",
                "RegistrationDate",
                "ReleaseDate",
                "ConvictionDate",
                "NCGeneralStatute",
                "NCGeneralStatuteDescription",
                "ConfinementSentence",
                "ProbationSentence",
                "CountyName",
                "AOCCourtCountyIdentifier",
                "ConvictionCountyName",
                "ConvictionState",
                "OffenseQualifierDescription",
                "AggravatedOffenseDescription",
                "OffenseDate",
                "VictimAge",
                "OffenseKey",
            ],
            [["0000001A", "2024-01-15", "", "2010-03-01", "14-27.21", "Indecent liberties", "", "", "Wake", "01", "Wake", "NC", "Qualifier", "", "2010-02-01", "12", "001"]],
        ),
        "Public Violation Information.txt": _fixed_width_table(
            ["SexRegistrationNumber", "ViolationType", "ViolationDescription"],
            [["0000001A", "FTC", "FAILURE TO NOTIFY OF ADDRESS CHANGE"]],
        ),
        "Public BirthDate Information.txt": _fixed_width_table(
            ["SexRegistrationNumber", "BirthDate"],
            [["0000001A", "1980-02-03"]],
        ),
        "Public Conviction Name Information.txt": _fixed_width_table(
            ["SexRegistrationNumber", "OffenseKey", "FullName", "Nametype"],
            [["0000001A", "001", "JOHN A DOE", "C"]],
        ),
        "Public ScarMarkTattoo Information.txt": _fixed_width_table(
            ["SexRegistrationNumber", "NCICScarMarkTattoo", "ScarMarkTattooText", "ScarMarkTattooDescription"],
            [["0000001A", "TAT", "LEFT ARM", "Tattoo"]],
        ),
        "Public NonResident Information.txt": _fixed_width_table(
            [
                "SexRegistrationNumber",
                "NonResidentInStateAddressLine1",
                "NonResidentInStateAddressLine2",
                "NonResidentInStateCity",
                "NonResidentInStateState",
                "NonResidentInStateZip",
                "NonResidentOutofStateAddressLine1",
                "NonResidentOutofStateAddressLine2",
                "NonResidentOutofStateCity",
                "NonResidentOutofStateState",
                "NonResidentOutofStateZip",
                "SchoolBusinessName",
            ],
            [["0000001A", "", "", "", "", "", "", "", "", "", "", ""]],
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return buffer.getvalue()


def _make_iowa_record(
    *,
    registrant: str,
    display_name: str,
    line_1: str,
    city: str,
    postal_code: str,
    county: str,
    tier: str,
    last_changed: str,
    photo: str,
) -> dict:
    return {
        "registrant": registrant,
        "oci": 114043,
        "last_name": display_name.split(",")[0],
        "first_name": display_name.split(",")[1].strip().split(" ")[0] if "," in display_name else display_name,
        "middle_name": "ALEX",
        "suffix": "",
        "gender": "MALE",
        "residency_restriction": "0",
        "employment_restriction": "1",
        "exclusion_zones": "1",
        "tier": tier,
        "county": county,
        "race": "White",
        "hair_color": "Black",
        "height_inches": 68,
        "weight_pounds": 230,
        "eye_color": "Brown",
        "skin_tone": "Fair",
        "display_name": display_name,
        "last_changed": last_changed,
        "line_1": line_1,
        "line_2": "",
        "city": city,
        "postal_code": postal_code,
        "lat": "41.69657135",
        "lon": "-93.64181519",
        "state": "Iowa",
        "birthdate": "01/09/1977",
        "photo": photo,
        "victim_minors": 1,
        "victim_adults": 1,
        "victim_unknown": 0,
        "registrant_cluster": "1",
        "address": f"{line_1}, {city}, Iowa {postal_code}",
        "wanted": "0",
        "distance": "Not Available",
        "convictions": [
            {
                "conviction": "Sexual abuse 3rd  degree",
                "conviction_date": "01/07/2011",
                "registrant_age": "33",
                "iowa_code": "709,4,1",
                "vehicle_used": "0",
                "county": county,
                "victims": [{"gender": "FEMALE", "age": "Adult (18+)"}],
            }
        ],
        "aliases": [
            {"last_name": "VASQUEZ", "first_name": "ADVINA", "middle_name": "ALEX"},
        ],
        "skin_markings": ["Tattooed Shoulder, left"],
        "photos": [photo],
    }


def _make_michigan_detail_html() -> str:
    return """
    <html>
      <body>
        <div class="row mt-2" id="offender-details">
          <div class="col-lg-2">
            <img class="rounded" style="width:100%" src="/api/file/image/test-photo-id" alt="Photo of offender" title="Photo of offender" />
          </div>
          <div class="col-lg-5">
            <div class="row">
              <div class="col text-right">Registration Number:</div>
              <div class="col font-weight-bold">6305507</div>
            </div>
            <div class="row">
              <div class="col text-right">MDOC #:</div>
              <div class="col font-weight-bold">0516588</div>
            </div>
            <div class="row">
              <div class="col text-right">Status:</div>
              <div class="col font-weight-bold">Active</div>
            </div>
            <div class="row">
              <div class="col text-right">Age:</div>
              <div class="col nowrap">
                <span class="font-weight-bold">42</span>
                <span>(DOB:</span>
                <span class="font-weight-bold">03/15/1984</span>
                <span>)</span>
              </div>
            </div>
            <div class="row">
              <div class="col text-right">Last Verification Date:</div>
              <div class="col font-weight-bold">03/06/2025</div>
            </div>
            <div class="row">
              <div class="col text-right">Compliance Status:</div>
              <div class="col font-weight-bold"><span>Compliant</span></div>
            </div>
            <div class="row">
              <div class="col text-right">Sex:</div>
              <div class="col font-weight-bold">FEMALE</div>
            </div>
            <div class="row">
              <div class="col text-right">Race:</div>
              <div class="col font-weight-bold">WHITE</div>
            </div>
            <div class="row">
              <div class="col text-right">Hair:</div>
              <div class="col font-weight-bold">SANDY</div>
            </div>
            <div class="row">
              <div class="col text-right">Height:</div>
              <div class="col font-weight-bold">6' 1"</div>
            </div>
            <div class="row">
              <div class="col text-right">Weight:</div>
              <div class="col font-weight-bold">185 lbs</div>
            </div>
            <div class="row">
              <div class="col text-right">Eyes:</div>
              <div class="col font-weight-bold">GREEN</div>
            </div>
          </div>
        </div>
        <div class="tab-pane fade show active" id="addresses" role="tabpanel">
          <div>
            <h3 class="h4 text-primary">Primary Address</h3>
            <div class="row">
              <div class="col">
                <span>2325 PRESQUE ISLE AVENUE</span><br />
                <span>APT 6</span><br />
                <span>MARQUETTE, Michigan 49855</span>
              </div>
            </div>
            <hr />
            <h3 class="h4 text-primary mt-2">Work Address</h3>
            <div class="row">
              <div class="col">
                <span>227 WEST WASHINGTON STREET</span><br />
                <span>MARQUETTE, Michigan 49855</span>
              </div>
            </div>
          </div>
        </div>
        <div class="tab-pane fade" id="aliases" role="tabpanel">
          <ul class="font-weight-bold">
            <li>DANIEL  HULINGS</li>
            <li>DANIEL WILLIAM HULINGS</li>
            <li>DANIEL WILLIAM GREEN</li>
          </ul>
        </div>
        <div class="tab-pane fade" id="offenses" role="tabpanel">
          <div class="row">
            <div class="col-lg-6">
              <div class="card">
                <div class="card-header">
                  <span>750.520E1G - CRIMINAL SEXUAL CONDUCT 4TH DEGREE (INCEST)</span>
                </div>
                <div class="card-body">
                  <div class="row">
                    <div class="col text-right">Date Convicted:</div>
                    <div class="col font-weight-bold"><span>09/14/2018</span></div>
                  </div>
                  <div class="row">
                    <div class="col text-right">Conviction State:</div>
                    <div class="col font-weight-bold">Michigan</div>
                  </div>
                  <div class="row">
                    <div class="col text-right">County:</div>
                    <div class="col font-weight-bold">CLINTON</div>
                  </div>
                  <div class="row">
                    <div class="col text-right">Court:</div>
                    <div class="col font-weight-bold">29TH CIR ST JOHNS</div>
                  </div>
                  <div class="row">
                    <div class="col text-right">Counts:</div>
                    <div class="col font-weight-bold">2</div>
                  </div>
                  <div class="row">
                    <div class="col text-right">Details:</div>
                    <div class="col font-weight-bold"></div>
                  </div>
                  <div class="row">
                    <div class="col text-right">Attempted:</div>
                    <div class="col font-weight-bold"><span>No</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="tab-pane fade" id="scarsmarkstattoos" role="tabpanel">
          <span>None Found</span>
        </div>
        <div class="tab-pane fade" id="vehicles" role="tabpanel">
          <table class="table table-striped compact dataTable no-footer no-hover-effect">
            <thead>
              <tr>
                <th scope="col">License Plate #</th>
                <th scope="col">Type</th>
                <th scope="col">Make</th>
                <th scope="col">Model</th>
                <th scope="col">Year</th>
                <th scope="col">Color</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>ETM2028</td>
                <td>STANDARD VEHICLE</td>
                <td>SUBARU</td>
                <td>FORESTER</td>
                <td>2011</td>
                <td>GRAY</td>
              </tr>
            </tbody>
          </table>
        </div>
      </body>
    </html>
    """.strip()


def _make_minnesota_detail_html() -> str:
    return """
    <html>
      <body>
        <div id="wrapper">
          <div>
            <h3 class="pageHeader">Ahles, Travis Kenneth</h3>
          </div>
          <div>
            <img src="PublicRegistrantSearchCache\\255642F.jpg" alt="Mugshot Front" class="mugshot" title="Mugshot Front" />
            <img src="PublicRegistrantSearchCache\\255642S.jpg" alt="Mugshot Side" class="mugshot" title="Mugshot Side" />
          </div>
          <div class="grayBorder" style="border-top-width:.14em">
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold paddingRight">Birth Date</span></div>
              <div class="td vMiddle"><span class="displayText">07/21/1995</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Race/Ethnicity</span></div>
              <div class="td vMiddle"><span class="displayText">White/Non Hispanic</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Skin Tone</span></div>
              <div class="td vMiddle"><span class="displayText">Olive</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Hair Color</span></div>
              <div class="td vMiddle"><span class="displayText">Brown</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Eye Color</span></div>
              <div class="td vMiddle"><span class="displayText">Brown</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Height</span></div>
              <div class="td vMiddle"><span class="displayText">5' 11"</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Weight</span></div>
              <div class="td vMiddle"><span class="displayText">145 lbs.</span></div>
            </div>
            <div class="row vMiddle noBorder">
              <div class="fixedWidthLabel"><span class="fontBold">Build</span></div>
              <div class="td vMiddle"><span class="displayText">Small</span></div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel"><span class="fontBold">Release Date</span></div>
              <div class="td vMiddle"><span class="displayText">03/25/2019</span></div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel"><span class="fontBold">Offense Statute(s)</span></div>
              <div class="td vMiddle"><span class="displayText">609.344</span></div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel alignTop"><span class="fontBold">Offense Information</span></div>
              <div class="td vMiddle"><span class="displayText">Travis Ahles engaged in sexual contact with a known female teenager.</span></div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel"><span class="fontBold">Address County</span></div>
              <div class="td vMiddle"><span class="displayText">MORRISON</span></div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel"><span class="fontBold">Registered Address</span></div>
              <div class="td vMiddle">
                <span class="displayText">Vicinity of 160th Avenue and Iris Road<br />rural Little Falls, MN 56345</span>
              </div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel alignTop"><span class="fontBold">Law Enforcement Agency</span></div>
              <div class="td vMiddle"><span class="displayText">Morrison County Sheriff's Office<br />320-632-9233</span></div>
            </div>
          </div>
          <div class="grayBorder">
            <div class="row vMiddle">
              <div class="fixedWidthLabel alignTop"><span class="fontBold">Also Known As Names</span></div>
              <div class="td vMiddle">
                <span class="displayText">TRAVIS KENNETH AHLES<br />TRAVIS AHLES</span>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """.strip()


def _make_nebraska_region_search_html() -> str:
    return """
    <html>
      <body>
        <input id="CountyId" />
        <script>
          kendo.syncReady(function(){jQuery("#CountyId").kendoDropDownList({"dataSource":[{"Text":"Douglas","Value":"594"}],"dataTextField":"Text","filter":"contains","dataValueField":"Value"});});
        </script>
      </body>
    </html>
    """.strip()


def _make_nebraska_search_results_html() -> str:
    return """
    <html>
      <body>
        <div>Showing results 1 - 1 of 1 | 1</div>
        <div class="result">
          <h2>Chad Michael Aaron</h2>
          <a href="/Registry/Offender/199912TLR">View Details</a>
          <a href="/Subscriptions/SubscribeToOffender?offenderId=25108">Notify Me</a>
        </div>
      </body>
    </html>
    """.strip()


def _make_nebraska_detail_html() -> str:
    return """
    <html>
      <head>
        <title>Nebraska Sex Offender Registry: Chad Michael Aaron</title>
      </head>
      <body>
        <h1 class="page-title">Chad Michael Aaron</h1>
        <div class="info_line"><span>Date of Birth:</span>5/10/1979</div>
        <div class="info_line"><span>Registration Duration:</span>Lifetime</div>
        <div class="info_line"><span>Race:</span>White</div>
        <div class="info_line"><span>Sex:</span>Male</div>
        <div class="info_line"><span>Height:</span>5' 8"</div>
        <div class="info_line"><span>Weight:</span>165 lbs</div>
        <div class="info_line"><span>Hair:</span>Gray or Partially Gray</div>
        <div class="info_line"><span>Eyes:</span>Blue</div>
        <div class="info_line"><span>Alias(s):</span>Chad M Aaron</div>
        <div id="addresses">
          <div class="address">
            Physical/Main Address<br />
            7873 Reddick Ave<br />
            Omaha, NE 68122<br />
            Douglas<br />
            <span> County</span><br />
            <span> Address Reported On:</span> 7/23/2019
          </div>
        </div>
        <div id="schools">
          <em>Offender attending:</em>
          <div><em>No schools listed</em></div>
        </div>
        <div id="vehicles">
          <dl>
            <dt>Truck: 2022 4-Door FORD EDGE , BLACK</dt>
            <dt>Truck: 2012 4-Door FORD FLEX , BLACK</dt>
          </dl>
        </div>
        <h2>Sex Crime Conviction(s)</h2>
        <hr />
        <div class="info_line"><span>Crime:</span>3rd Degree Sexual Assault M1</div>
        <div class="info_line"><span>Statute Number(s):</span>28-320(3)</div>
        <div class="info_line"><span>Jurisdiction:</span>Madison</div>
        <div class="info_line"><span>Court:</span>District</div>
        <div class="info_line"><span>Conviction Date:</span>8/3/1999</div>
        <div class="info_line"><span>Place of Crime:</span>NE</div>
        <div class="info_line"><span>Victim of Crime:</span>Minor</div>
        <hr />
        <div class="info_line"><span>Crime:</span>Sexual Assault of a Child F3A</div>
        <div class="info_line"><span>Statute Number(s):</span>28-320.01</div>
        <div class="info_line"><span>Jurisdiction:</span>Madison</div>
        <div class="info_line"><span>Court:</span>District</div>
        <div class="info_line"><span>Conviction Date:</span>6/19/2000</div>
        <div class="info_line"><span>Place of Crime:</span>NE</div>
        <div class="info_line"><span>Victim of Crime:</span>Minor</div>
        <hr />
        <div class="info">
          <p>This public notification is to inform you that the following person is registered with the Nebraska Sex Offender Registry (SOR).</p>
        </div>
        <img src="/Image/11193" alt="Chad Michael Aaron" />
      </body>
    </html>
    """.strip()


def _make_missouri_zip_bytes() -> bytes:
    def _workbook_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
        workbook = Workbook()
        worksheet = workbook.active
        for _ in range(13):
            worksheet.append([])
        worksheet.append(headers)
        for row in rows:
            worksheet.append(row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    master_headers = [
        "Name",
        "Address",
        "City",
        "St",
        "Zip",
        "County",
        "Offense",
        "Count",
        "Compliant",
        "Tier",
        "Date of Birth",
    ]
    offense_headers = [
        "Name",
        "Address",
        "City",
        "St",
        "Zip",
        "County",
        "Offense",
        "Offense City",
        "Offense State",
        "Victim Gender",
        "Victim Age",
        "Victim Max Age",
        "Compliant",
        "Tier",
        "Date of Birth",
        "Offense Date",
        "Conviction Date",
        "Confinement Release Date",
        "Probation/Parole Release Date",
        "Offender Age at Time of Offense",
    ]
    alias_headers = [
        "Name",
        "Address",
        "City",
        "St",
        "Zip",
        "County",
        "Compliant",
        "Tier",
        "Date of Birth",
    ]
    vehicle_html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Name</th><th>Vehicle Make</th><th>Vehicle Model</th><th>Vehicle Color Code</th><th>Vehicle Color</th><th>License Year</th><th>License</th><th>License State</th><th>Vehicle Owner</th><th>Address</th><th>City</th><th>St</th><th>Zip</th><th>County</th><th>Offense</th><th>Count</th><th>Compliant</th><th>Tier</th><th>Date of Birth</th>
          </tr>
          <tr>
            <td>DOE, JOHN A</td><td>CHEVROLET</td><td>IMPALA</td><td>BLK</td><td>BLACK</td><td>2018</td><td>ABC123</td><td>MO</td><td>Y</td><td>123 MAIN ST</td><td>ST LOUIS</td><td>MO</td><td>63101</td><td>ST LOUIS CITY</td><td>STATUTORY SODOMY</td><td>1</td><td>Y</td><td>3</td><td>1984/01/02</td>
          </tr>
          <tr>
            <td>DOE, JOHN A</td><td>FORD</td><td>ESCAPE</td><td>RED</td><td>RED</td><td>2020</td><td>XYZ789</td><td>MO</td><td>Y</td><td>123 MAIN ST</td><td>ST LOUIS</td><td>MO</td><td>63101</td><td>ST LOUIS CITY</td><td>STATUTORY SODOMY</td><td>1</td><td>Y</td><td>3</td><td>1984/01/02</td>
          </tr>
        </table>
      </body>
    </html>
    """.strip()

    master_rows = [
        [
            "DOE, JOHN A",
            "123 MAIN ST",
            "ST LOUIS",
            "MO",
            "63101",
            "ST LOUIS CITY",
            "STATUTORY SODOMY",
            1,
            "Y",
            3,
            "1984/01/02",
        ],
        [
            "DOE, JOHN A",
            "123 MAIN ST",
            "ST LOUIS",
            "MO",
            "63101",
            "ST LOUIS CITY",
            "STATUTORY RAPE",
            1,
            "Y",
            3,
            "1984/01/02",
        ],
    ]
    offense_rows = [
        [
            "DOE, JOHN A",
            "123 MAIN ST",
            "ST LOUIS",
            "MO",
            "63101",
            "ST LOUIS CITY",
            "STATUTORY SODOMY",
            "ST LOUIS",
            "MO",
            "M",
            "14",
            ".",
            "Y",
            "3",
            "1984/01/02",
            "2002/01/01",
            "2003/01/01",
            "2005/01/01",
            "2006/01/01",
            17,
        ],
        [
            "DOE, JOHN A",
            "123 MAIN ST",
            "ST LOUIS",
            "MO",
            "63101",
            "ST LOUIS CITY",
            "STATUTORY RAPE",
            "ST LOUIS",
            "MO",
            "F",
            "13",
            ".",
            "Y",
            "3",
            "1984/01/02",
            "2004/01/01",
            "2005/01/01",
            "",
            "",
            19,
        ],
    ]
    alias_rows = [
        [
            "JOHN A DOE",
            "123 MAIN ST",
            "ST LOUIS",
            "MO",
            "63101",
            "ST LOUIS CITY",
            "Y",
            3,
            "1984/01/02",
        ],
        [
            "J DOE",
            "123 MAIN ST",
            "ST LOUIS",
            "MO",
            "63101",
            "ST LOUIS CITY",
            "Y",
            3,
            "1984/01/02",
        ],
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("msor.xlsx", _workbook_bytes(master_headers, master_rows))
        archive.writestr("msor_offense.xlsx", _workbook_bytes(offense_headers, offense_rows))
        archive.writestr("msor_alias.xlsx", _workbook_bytes(alias_headers, alias_rows))
        archive.writestr("msor_veh.xls", vehicle_html.encode("windows-1252"))
    return buffer.getvalue()


def _sqlite_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _register_spatialite_functions(dbapi_connection, _connection_record):
        dbapi_connection.create_function("RecoverGeometryColumn", 5, lambda *args: 1)
        dbapi_connection.create_function("AddGeometryColumn", 6, lambda *args: 1)
        dbapi_connection.create_function("DiscardGeometryColumn", 2, lambda *args: 1)
        dbapi_connection.create_function("CreateSpatialIndex", 2, lambda *args: 1)
        dbapi_connection.create_function("DisableSpatialIndex", 2, lambda *args: 1)
        dbapi_connection.create_function("EnableSpatialIndex", 2, lambda *args: 1)
        dbapi_connection.create_function("CheckSpatialIndex", 1, lambda *args: 1)
        dbapi_connection.create_function("GeomFromEWKT", 1, lambda value: value)
        dbapi_connection.create_function("AsEWKB", 1, lambda value: value)
        dbapi_connection.create_function("AsEWKT", 1, lambda value: value)

    return engine


def test_persist_normalized_records_upserts_and_replaces_children() -> None:
    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
        ],
    )

    run_id = uuid4()
    with Session(engine) as session:
        session.add(
            IngestionRun(
                id=run_id,
                source_name="florida",
                source_state="FL",
                status="running",
            )
        )
        session.commit()

        first = persist_normalized_records(
            session,
            source_name="florida",
            source_state="FL",
            ingestion_run_id=run_id,
            normalized_records=[
                {
                    "external_id": "florida:001",
                    "full_name": "Example Person",
                    "risk_level": "high",
                    "date_of_birth": "1980-01-01",
                    "offenses": [
                        {
                            "offense_name": "Example offense",
                            "statute": "775.21",
                            "offense_date": "2020-01-01",
                        }
                    ],
                    "raw_payload": {"external_id": "florida:001"},
                }
            ],
            dry_run=False,
        )

        second = persist_normalized_records(
            session,
            source_name="florida",
            source_state="FL",
            ingestion_run_id=run_id,
            normalized_records=[
                {
                    "external_id": "florida:001",
                    "full_name": "Updated Person",
                    "risk_level": "moderate",
                    "offenses": [
                        {
                            "offense_name": "Updated offense",
                            "statute": "794.011",
                            "offense_date": "2021-01-01",
                        }
                    ],
                    "raw_payload": {"external_id": "florida:001", "updated": True},
                }
            ],
            dry_run=False,
        )

        registrants = session.exec(select(Registrant)).all()
        source_records = session.exec(select(SourceRecord)).all()
        offenses = session.exec(select(Offense)).all()

    assert first["records_seen"] == 1
    assert second["records_seen"] == 1
    assert len(registrants) == 1
    assert registrants[0].full_name == "Updated Person"
    assert len(source_records) == 1
    assert source_records[0].normalized_payload["full_name"] == "Updated Person"
    assert len(offenses) == 1
    assert offenses[0].offense_name == "Updated offense"


class BatchedConnector(SourceConnector):
    name = "test-batched"
    state = "TS"
    source_url = "https://example.com"

    async def fetch(self, *, limit: int | None = None) -> list[dict]:
        return []

    async def fetch_batches(self, *, limit: int | None = None, batch_size: int | None = None, cursor: str | None = None):
        yield (
            [
                {
                    "external_id": "test-batched:001",
                    "full_name": "Batch One",
                    "offenses": [{"offense_name": "Batch offense one"}],
                    "raw_payload": {"batch": 1},
                }
            ],
            "cursor-one",
        )
        yield (
            [
                {
                    "external_id": "test-batched:002",
                    "full_name": "Batch Two",
                    "offenses": [{"offense_name": "Batch offense two"}],
                    "raw_payload": {"batch": 2},
                }
            ],
            None,
        )

    def parse(self, raw_payloads: list[dict]) -> list[dict]:
        return raw_payloads

    def normalize(self, parsed_records: list[dict]) -> list[dict]:
        return parsed_records


def test_ingest_source_tracks_checkpoint_and_batches(monkeypatch) -> None:
    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    connector = BatchedConnector()
    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "test-batched", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrants = session.exec(select(Registrant).order_by(Registrant.external_id)).all()
        source_records = session.exec(select(SourceRecord).order_by(SourceRecord.external_id)).all()

    assert run.status == "completed"
    assert run.completed_at is not None
    assert checkpoint.completed_at is not None
    assert checkpoint.cursor is None
    assert checkpoint.last_external_id == "test-batched:002"
    assert checkpoint.details["batch_index"] == 2
    assert [row.external_id for row in registrants] == ["test-batched:001", "test-batched:002"]
    assert [row.external_id for row in source_records] == ["test-batched:001", "test-batched:002"]


def test_florida_connector_ingests_csv_batches(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "florida.csv"
    csv_path.write_text(
        "id,full_name,address,city,county,zip,offense,statute,dob\n"
        "fl-001,Example Person,123 Main St,Tallahassee,Leon,32301,Example offense,794.011,1980-01-01\n"
        "fl-002,Second Person,456 Oak Ave,Orlando,Orange,32801,Second offense,775.21,1979-05-05\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(FloridaRegistryCsvConnector.csv_env_var, str(csv_path))
    connector = FloridaRegistryCsvConnector()

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "florida", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrants = session.exec(select(Registrant).order_by(Registrant.external_id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "fl-002"
    assert len(registrants) == 2
    assert registrants[0].full_name == "Example Person"


def test_north_carolina_connector_ingests_zip_batches(monkeypatch) -> None:
    archive_bytes = _make_north_carolina_zip_bytes()
    connector = NorthCarolinaRegistryConnector()

    async def fake_download_archive(self):
        return archive_bytes

    monkeypatch.setattr(NorthCarolinaRegistryConnector, "_download_archive", fake_download_archive)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "north-carolina", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address)).all()
        aliases = session.exec(select(Alias)).all()
        offenses = session.exec(select(Offense)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "0000001A"
    assert registrant.external_id == "0000001A"
    assert registrant.full_name == "DOE,JOHN A"
    assert len(addresses) == 2
    assert len(aliases) == 1
    assert aliases[0].alias_name == "JOHN A DOE"
    assert len(offenses) == 1
    assert offenses[0].offense_name == "Indecent liberties"


def test_iowa_connector_ingests_json_batches(monkeypatch) -> None:
    connector = IowaRegistryApiConnector()
    pages = {
        1: {
            "page": 1,
            "pages": 2,
            "onpage": 1,
            "results": 2,
            "records": [
                _make_iowa_record(
                    registrant="7",
                    display_name="VASQUEZ, ADIVINO ALEX ",
                    line_1="3214 SW BROOKELINE DR",
                    city="ANKENY",
                    postal_code="50023",
                    county="Polk",
                    tier="Tier 3, Quarterly Reviews",
                    last_changed="01/22/2026",
                    photo="https://www.iowasexoffender.gov/api/photo/photoimagebyid/92755",
                ),
            ],
        },
        2: {
            "page": 2,
            "pages": 2,
            "onpage": 1,
            "results": 2,
            "records": [
                _make_iowa_record(
                    registrant="8",
                    display_name="SMITH, JANE",
                    line_1="100 MAIN ST",
                    city="DES MOINES",
                    postal_code="50309",
                    county="Polk",
                    tier="Tier 2, Semiannual Reviews",
                    last_changed="01/15/2026",
                    photo="https://www.iowasexoffender.gov/api/photo/photoimagebyid/11111",
                ),
            ],
        },
    }

    async def fake_fetch_page(self, *, page: int, per_page: int, params: dict | None = None):
        return pages[page]

    monkeypatch.setattr(IowaRegistryApiConnector, "_fetch_page", fake_fetch_page)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "iowa", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrants = session.exec(select(Registrant).order_by(Registrant.external_id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "8"
    assert [row.external_id for row in registrants] == ["7", "8"]
    assert registrants[0].full_name == "VASQUEZ, ADIVINO ALEX"
    assert len(photos) == 2
    assert offenses[0].offense_name == "Sexual abuse 3rd  degree"


def test_michigan_connector_ingests_search_and_detail_batches(monkeypatch) -> None:
    connector = MichiganRegistryConnector()
    search_payload = {
        "draw": 1,
        "recordsTotal": 1,
        "recordsFiltered": 1,
        "totalItems": 1,
        "offenders": [
            {
                "id": "48bc28ee-8e67-415e-811e-7f3b443225e2",
                "firstName": "DANIEL",
                "middleName": "WILLIAM",
                "lastName": "HULINGS",
                "age": 42,
                "imageUrl": "/api/file/image/test-photo-id",
                "compliant": "Compliant",
                "street": "2325 PRESQUE ISLE AVENUE",
                "city": "MARQUETTE",
                "postalCode": "49855",
                "county": "Marquette",
            }
        ],
    }
    detail_html = _make_michigan_detail_html()

    async def fake_fetch_search_page(self, client, *, start: int, length: int):
        return search_payload

    async def fake_fetch_detail_html(self, client, offender_id: str):
        assert offender_id == "48bc28ee-8e67-415e-811e-7f3b443225e2"
        return detail_html

    monkeypatch.setattr(MichiganRegistryConnector, "_fetch_search_page", fake_fetch_search_page)
    monkeypatch.setattr(MichiganRegistryConnector, "_fetch_detail_html", fake_fetch_detail_html)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "michigan", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "48bc28ee-8e67-415e-811e-7f3b443225e2"
    assert registrant.external_id == "48bc28ee-8e67-415e-811e-7f3b443225e2"
    assert registrant.full_name == "HULINGS, DANIEL WILLIAM"
    assert registrant.date_of_birth.isoformat() == "1984-03-15"
    assert registrant.risk_level == "Compliant"
    assert len(addresses) == 2
    assert addresses[0].city == "MARQUETTE"
    assert len(aliases) == 3
    assert {row.alias_name for row in aliases} == {
        "DANIEL HULINGS",
        "DANIEL WILLIAM HULINGS",
        "DANIEL WILLIAM GREEN",
    }
    assert len(offenses) == 1
    assert offenses[0].offense_name == "CRIMINAL SEXUAL CONDUCT 4TH DEGREE (INCEST)"
    assert offenses[0].statute == "750.520E1G"
    assert len(photos) == 1
    assert photos[0].image_url == "/api/file/image/test-photo-id"


def test_minnesota_connector_ingests_grid_and_detail_batches(monkeypatch) -> None:
    connector = MinnesotaRegistryConnector()
    group_10 = [
        {
            "OffenderName": "Ahles, Travis Kenneth",
            "MoveDate": "/Date(1659243600000)/",
            "id": 255642,
            "group": 10,
        }
    ]

    async def fake_fetch_group_results(self, client, group: int):
        return group_10 if group == 10 else []

    async def fake_fetch_detail_html(self, client, offender_id: int, *, group: int):
        assert offender_id == 255642
        assert group == 10
        return _make_minnesota_detail_html()

    monkeypatch.setattr(MinnesotaRegistryConnector, "_fetch_group_results", fake_fetch_group_results)
    monkeypatch.setattr(MinnesotaRegistryConnector, "_fetch_detail_html", fake_fetch_detail_html)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "minnesota", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "255642"
    assert registrant.external_id == "255642"
    assert registrant.full_name == "Ahles, Travis Kenneth"
    assert registrant.date_of_birth.isoformat() == "1995-07-21"
    assert len(addresses) == 1
    assert addresses[0].city == "rural Little Falls"
    assert len(aliases) == 2
    assert {row.alias_name for row in aliases} == {"TRAVIS KENNETH AHLES", "TRAVIS AHLES"}
    assert len(offenses) == 1
    assert offenses[0].statute == "609.344"
    assert "sexual contact" in offenses[0].offense_name.lower()
    assert len(photos) == 2


def test_missouri_connector_ingests_bulk_archive_batches(monkeypatch) -> None:
    connector = MissouriRegistryConnector()
    archive_bytes = _make_missouri_zip_bytes()

    async def fake_download_archive(self):
        return archive_bytes

    monkeypatch.setattr(MissouriRegistryConnector, "_download_archive", fake_download_archive)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "missouri", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == registrant.external_id
    assert registrant.full_name == "DOE, JOHN A"
    assert registrant.date_of_birth.isoformat() == "1984-01-02"
    assert registrant.risk_level == "Tier 3"
    assert len(addresses) == 1
    assert addresses[0].city == "ST LOUIS"
    assert len(aliases) == 2
    assert {row.alias_name for row in aliases} == {"JOHN A DOE", "J DOE"}
    assert len(offenses) == 2
    assert {row.offense_name for row in offenses} == {"STATUTORY SODOMY", "STATUTORY RAPE"}
    assert len(photos) == 0
    assert registrant.demographics["vehicle_count"] == 2


def test_south_dakota_connector_ingests_full_registry_export(monkeypatch) -> None:
    connector = SouthDakotaRegistryConnector()
    payload = {
        "Total": 1,
        "Results": [
            {
                "Id": 1,
                "FirstName": "TROY",
                "LastName": "AADLAND",
                "FullName": "TROY SCOTT AADLAND",
                "Address": "301 WALNUT AVENUE",
                "City": "TRENT",
                "ZipCode": "57065",
                "Latitude": 43.9052,
                "Longitude": -96.656975,
                "IsInJail": False,
                "ImageFileName": "1FACE2025811_81314.jpg",
                "ImageDate": "2025-08-11T00:00:00",
                "County": "MOODY",
                "Ori": None,
                "DateOfBirth": "02/25/1967",
                "LatLng": [43.9052, -96.656975],
            }
        ],
    }

    async def fake_fetch_full_registry(self):
        return payload

    monkeypatch.setattr(SouthDakotaRegistryConnector, "_fetch_full_registry", fake_fetch_full_registry)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "south-dakota", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "sd:1"
    assert registrant.full_name == "TROY SCOTT AADLAND"
    assert registrant.date_of_birth.isoformat() == "1967-02-25"
    assert len(addresses) == 1
    assert addresses[0].city == "TRENT"
    assert addresses[0].county == "MOODY"
    assert len(aliases) == 0
    assert len(offenses) == 0
    assert len(photos) == 1
    assert photos[0].image_url == "https://sor.sd.gov/sorfiles/OffenderImages/1FACE2025811_81314.jpg"
    assert photos[0].captured_at is not None
    assert photos[0].captured_at.date().isoformat() == "2025-08-11"


def test_nebraska_connector_ingests_region_search_batches(monkeypatch) -> None:
    connector = NebraskaRegistryConnector()

    async def fake_fetch_counties(self, client):
        return [{"name": "Douglas", "id": "594"}]

    async def fake_fetch_search_page(self, client, *, county_id: str, page: int):
        assert county_id == "594"
        assert page == 1
        return _make_nebraska_search_results_html()

    async def fake_fetch_detail_html(self, client, detail_url: str):
        assert detail_url.endswith("/Registry/Offender/199912TLR")
        return _make_nebraska_detail_html()

    monkeypatch.setattr(NebraskaRegistryConnector, "_fetch_counties", fake_fetch_counties)
    monkeypatch.setattr(NebraskaRegistryConnector, "_fetch_search_page", fake_fetch_search_page)
    monkeypatch.setattr(NebraskaRegistryConnector, "_fetch_detail_html", fake_fetch_detail_html)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "nebraska", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "ne:199912TLR"
    assert registrant.full_name == "Chad Michael Aaron"
    assert registrant.date_of_birth.isoformat() == "1979-05-10"
    assert registrant.risk_level == "Lifetime"
    assert len(addresses) == 1
    assert addresses[0].line1 == "7873 Reddick Ave"
    assert addresses[0].city == "Omaha"
    assert addresses[0].county == "Douglas"
    assert len(aliases) == 1
    assert aliases[0].alias_name == "Chad M Aaron"
    assert len(offenses) == 2
    assert {row.offense_name for row in offenses} == {
        "3rd Degree Sexual Assault M1",
        "Sexual Assault of a Child F3A",
    }
    assert len(photos) == 1
    assert photos[0].image_url == "https://sor.nebraska.gov/Image/11193"
    assert registrant.demographics["vehicle_count"] == 2


def _make_north_dakota_search_results_html() -> str:
    return """
    <html>
      <body>
        <table id="tblOffender">
          <tbody>
            <tr>
              <td><img data-original="https://sexoffender.nd.gov/photos/test.jpg" alt="DOE, JOHN" /></td>
              <td>
                DOE, JOHN
                <div class="mt-1"><a class="ag-link" href="/offender/details/123e4567-e89b-12d3-a456-426614174000">View Details</a></div>
              </td>
              <td>1990</td>
              <td>
                <address>
                  123 MAIN ST<br />
                  BISMARCK, ND, 58501<br />
                  BURLEIGH<br />
                  <a href="/offender/map-single/123e4567-e89b-12d3-a456-426614174000?addressId=addr-1">Show Map</a>
                </address>
              </td>
              <td>HIGH</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """.strip()


def _make_north_dakota_detail_html() -> str:
    return """
    <html>
      <head>
        <title>Offender Profile</title>
      </head>
      <body>
        <div class="card">
          <div class="card-header">Offender</div>
          <div class="card-body">
            <img id="primaryImgId" src="https://sexoffender.nd.gov/photos/profile.jpg" alt="DOE, JOHN photo" />
          </div>
        </div>
        <div class="card">
          <div class="card-header">Primary Information</div>
          <div class="card-body">
            <dl class="row">
              <dt class="col-sm-3">Name:</dt><dd class="col-sm-9">DOE, JOHN</dd>
              <dt class="col-sm-3">Aliases:</dt><dd class="col-sm-9">JOHN DOE<br/>J DOE</dd>
              <dt class="col-sm-3">Birthdate:</dt><dd class="col-sm-9">1990</dd>
              <dt class="col-sm-3">Sex:</dt><dd class="col-sm-9">MALE</dd>
              <dt class="col-sm-3">Race:</dt><dd class="col-sm-9">WHITE</dd>
              <dt class="col-sm-3">Height:</dt><dd class="col-sm-9">5' 8"</dd>
              <dt class="col-sm-3">Weight:</dt><dd class="col-sm-9">220 LBS</dd>
              <dt class="col-sm-3">Eye Color:</dt><dd class="col-sm-9">BROWN</dd>
              <dt class="col-sm-3">Hair Color:</dt><dd class="col-sm-9">BLACK</dd>
              <dt class="col-sm-3">Skin:</dt><dd class="col-sm-9">LIGHT</dd>
              <dt class="col-sm-3">Registration Expiration:</dt><dd class="col-sm-9">12/31/2030</dd>
              <dt class="col-sm-3">Risk Level:</dt><dd class="col-sm-9">HIGH</dd>
              <dt class="col-sm-3">Registration Status:</dt><dd class="col-sm-9">ACTIVE</dd>
              <dt class="col-sm-3">Ethnicity:</dt><dd class="col-sm-9">NOT HISPANIC OR LATINO</dd>
            </dl>
          </div>
        </div>
        <div class="card">
          <div class="card-header">Address Information</div>
          <div class="card-body">
            <div class="card">
              <div class="card-header">Residence Addresses</div>
              <div class="card-body">
                <address>
                  123 MAIN ST<br />
                  BISMARCK, ND, 58501<br />
                  BURLEIGH<br />
                  <a href="/offender/map-single/123e4567-e89b-12d3-a456-426614174000?addressId=addr-1">Show Map</a>
                </address>
              </div>
            </div>
            <div class="card">
              <div class="card-header">Employer Addresses</div>
              <div class="card-body">
                <address>
                  456 SIDE ST<br />
                  BISMARCK, ND, 58501<br />
                  BURLEIGH<br />
                  <a href="/offender/map-single/123e4567-e89b-12d3-a456-426614174000?addressId=addr-2">Show Map</a>
                </address>
              </div>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">Qualifying Offense Information</div>
          <div class="card-body">
            <div class="list-group">
              <div class="list-group-item">
                <dl class="row mb-0">
                  <dt class="col-sm-3">Offense:</dt><dd class="col-sm-9">LURING MINOR BY COMPUTER; 12.1-20-05.1</dd>
                  <dt class="col-sm-3">Conviction Date:</dt><dd class="col-sm-9">11/25/2025</dd>
                  <dt class="col-sm-3">Jurisdiction &amp; State:</dt><dd class="col-sm-9">BURLEIGH COUNTY DISTRICT COURT, ND</dd>
                  <dt class="col-sm-3">Disposition:</dt><dd class="col-sm-9">5 YEARS; SERVE 2 YEARS</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">Vehicles</div>
          <div class="card-body">
            <div class="accordion" id="accordionVehicle">
              <div class="accordion-item">
                <div class="accordion-body">
                  <table class="table table-striped">
                    <thead>
                      <tr><th>Make</th><th>Color</th><th>Year</th><th>Plate Number</th></tr>
                    </thead>
                    <tbody>
                      <tr><td>FORD</td><td>BLACK</td><td>2018</td><td>ND-1234</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """.strip()


def _make_texas_county_search_page_html() -> str:
    return """
    <html>
      <body>
        <form method="post">
          <input type="hidden" name="__RequestVerificationToken" value="tx-token" />
          <select name="COU_COD">
            <option value="">Choose one...</option>
            <option value="001">ANDERSON</option>
          </select>
        </form>
      </body>
    </html>
    """.strip()


def _make_texas_county_results_html() -> str:
    return """
    <html>
      <body>
        <table id="tblExportDownloads" class="table table-striped">
          <tbody>
            <tr>
              <td>County</td>
              <td>Number of Results</td>
              <td>ANDERSON</td>
              <td>1</td>
            </tr>
          </tbody>
        </table>
        <table id="tblExportDownloads" class="table table-striped table-boarder">
          <thead>
            <tr>
              <th>Name</th><th>Birth Date</th><th>Sex</th><th>Race</th><th>Address</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <a href="/PublicSite/Search/Rapsheet?Sid=17361344" data-dpsnbr="17361344" data-hasphoto="True" data-sex="M" data-race="W" data-height="*" data-weight="*">
                  SANDERS,ALTON JAKE
                </a>
              </td>
              <td>02/09/2004</td>
              <td>M</td>
              <td>W</td>
              <td>160 COUNTY ROAD 1059 , ELKHART TX 75839</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """.strip()


def _make_texas_rapsheet_xml() -> str:
    return """
    <INDV>
      <DPS_NBR>17361344</DPS_NBR>
      <RSK_COD_LIT>MODERATE</RSK_COD_LIT>
      <ERT_COD_LIT>LIFETIME</ERT_COD_LIT>
      <VRP_COD_LIT>ANNUALLY</VRP_COD_LIT>
      <SEX_COD_LIT>Male</SEX_COD_LIT>
      <RAC_COD_LIT>White</RAC_COD_LIT>
      <ETH_COD_LIT>Non-Hispanic</ETH_COD_LIT>
      <HGT_QTY_formatted>5'9\"</HGT_QTY_formatted>
      <WGT_QTY>150</WGT_QTY>
      <HAI_COD_LIT>BROWN</HAI_COD_LIT>
      <EYE_COD_LIT>BROWN</EYE_COD_LIT>
      <SSZ_COD_formatted>11.5</SSZ_COD_formatted>
      <SWD_COD_formatted>UNKNOWN</SWD_COD_formatted>
      <IND_IDN>18360995</IND_IDN>
      <Names>
        <Name><TYP_COD>B</TYP_COD><NAM_TXT>SANDERS,ALTON JAKE</NAM_TXT></Name>
        <Name><TYP_COD>S</TYP_COD><NAM_TXT>AJ,XX</NAM_TXT></Name>
        <Name><TYP_COD>S</TYP_COD><NAM_TXT>SANDERS,ALTON JAMES</NAM_TXT></Name>
        <Name><TYP_COD>S</TYP_COD><NAM_TXT>JOYCE,ALTON JAMES</NAM_TXT></Name>
        <Name><TYP_COD>S</TYP_COD><NAM_TXT>A,J</NAM_TXT></Name>
      </Names>
      <Birthdates>
        <Birthdate><TYP_COD>B</TYP_COD><DOB_DTE_formatted>02/09/2004</DOB_DTE_formatted></Birthdate>
      </Birthdates>
      <RegistrationEvents>
        <RegistrationEvent><EVT_DTE_formatted>09/15/2023</EVT_DTE_formatted><EventId>21852253</EventId><EVM_COD_LIT>Change of Status</EVM_COD_LIT><ORI_TXT>TX2120000</ORI_TXT><ATR_TXT>SMITH CO SO TYLER</ATR_TXT></RegistrationEvent>
        <RegistrationEvent><EVT_DTE_formatted>03/01/2023</EVT_DTE_formatted><EventId>21742376</EventId><EVM_COD_LIT>Verification</EVM_COD_LIT><ORI_TXT>TX2120000</ORI_TXT><ATR_TXT>SMITH CO SO TYLER</ATR_TXT></RegistrationEvent>
      </RegistrationEvents>
      <Addresses>
        <Address>
          <CRT_TMS_formatted>10/18/2023</CRT_TMS_formatted>
          <PDV_COD_LIT>ACTIVE</PDV_COD_LIT>
          <AddressLine1>160 COUNTY ROAD 1059</AddressLine1>
          <AddressLine2 />
        </Address>
      </Addresses>
      <Offenses>
        <Offense>
          <LEN_TXT>AGGRAVATED SEXUAL ASSAULT OF A CHILD</LEN_TXT>
          <SOV_COD_LIT>Female</SOV_COD_LIT>
          <AOV_NBR>12</AOV_NBR>
          <CPR_COD>VAL</CPR_COD>
          <CPR_COD_LIT>LENGTH OF SENTENCE</CPR_COD_LIT>
          <CPR_VAL>10Y</CPR_VAL>
          <CDD_DTE>02/09/2023</CDD_DTE>
          <DIS_FLG>N</DIS_FLG>
          <OST_COD_LIT>PROBATION/COMMUNITY SUPERVISION</OST_COD_LIT>
          <CIT_TXT>TEXAS PENAL CODE 22.021(a)(1)(B)</CIT_TXT>
        </Offense>
      </Offenses>
      <Photos>
        <Photo>
          <PhotoId>10689396</PhotoId>
          <CUR_FLG>Y</CUR_FLG>
          <SOP_COD>CCH</SOP_COD>
          <POS_DTE_formatted>10/17/2023</POS_DTE_formatted>
        </Photo>
        <Photo>
          <PhotoId>10689397</PhotoId>
          <CUR_FLG>N</CUR_FLG>
          <SOP_COD>CCH</SOP_COD>
          <POS_DTE_formatted>09/17/2023</POS_DTE_formatted>
        </Photo>
      </Photos>
      <Notices>
        <Notice>DPS Cannot guarantee the records you obtain through this site relate to the person about whom you are seeking information.</Notice>
        <Notice>The registry contains information as reported by the law enforcement agency that served as the offender's last Texas registration authority.</Notice>
      </Notices>
    </INDV>
    """.strip()


def test_wisconsin_connector_ingests_name_search_prefix_batches(monkeypatch) -> None:
    connector = WisconsinRegistryConnector()
    search_calls: list[str] = []

    search_result = {
        "id": 100,
        "docNum": "WI-100",
        "fullName": "DOE, JOHN",
        "primaryResidence": {
            "city": "Milwaukee",
            "county": "Milwaukee County",
            "id": 1,
            "lat": "43.0123",
            "lon": "-87.9876",
            "state": "WI",
            "street1": "123 MAIN ST",
            "street2": None,
            "street3": "Milwaukee, WI 53202",
            "zip": "53202",
        },
    }
    detail_payload = {
        "offenderId": "100",
        "docNum": "WI-100",
        "fullName": "DOE, JOHN",
        "gender": "Male",
        "race": "White",
        "age": "41",
        "ethnicity": "Non Hispanic or Latino",
        "height": "5' 8\"",
        "weight": "180 lbs.",
        "eyeColor": "BROWN",
        "hairColor": "BLACK",
        "aliases": ["DOE, J"],
        "photoId": "999",
        "photoTaken": "2024-01-02T03:04",
        "registrationStart": "2020-01-01 00:00:00",
        "registrationEnd": "2030-01-01 00:00:00",
        "registrationTerm": "15 Years",
        "complianceStatus": "COMPLIANT",
        "supervisionStatus": "Community supervision",
        "primary": {
            "street": "123 MAIN ST",
            "city": "Milwaukee",
            "county": "Milwaukee County",
            "latitude": "43.0123",
            "longitude": "-87.9876",
            "state": "WI",
            "zip": "53202",
        },
        "verifiedNote": "Verified address",
        "mailResponse": "No",
        "offenses": [
            {
                "convictionDate": "2020-01-01 00:00:00",
                "offenseCode": "948.02",
                "offenseText": "Test Offense",
            }
        ],
        "otherAddress": {
            "label": "Office currently supervising offender:",
            "name": "FIELD SUPERVISOR",
            "address": {
                "street1": "4041 N RICHARDS ST",
                "city": "Milwaukee",
                "state": "WI",
                "zip": "53212",
                "phone": "414-229-0400",
            },
        },
    }

    async def fake_fetch_name_search(self, client, *, last: str, first: str | None = None, middle: str | None = None):
        search_calls.append(last)
        if last == "A":
            raise _SearchTooBroad("Search generated more than 240 results. Enter additional criteria to narrow the search.")
        if last == "AA":
            return [search_result]
        return []

    async def fake_fetch_offender_detail(self, client, offender_id: str):
        assert offender_id == "100"
        return detail_payload

    monkeypatch.setattr(WisconsinRegistryConnector, "_fetch_name_search", fake_fetch_name_search)
    monkeypatch.setattr(WisconsinRegistryConnector, "_fetch_offender_detail", fake_fetch_offender_detail)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "wisconsin", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert "A" in search_calls
    assert "AA" in search_calls
    assert run.status == "completed"
    assert checkpoint.last_external_id == "wi:100"
    assert registrant.full_name == "DOE, JOHN"
    assert registrant.risk_level == "15 Years"
    assert registrant.height_cm == 173
    assert registrant.weight_kg == 82
    assert registrant.sex == "Male"
    assert len(addresses) == 2
    addresses_by_line1 = {address.line1: address for address in addresses}
    assert addresses_by_line1["123 MAIN ST"].city == "Milwaukee"
    assert addresses_by_line1["123 MAIN ST"].county == "Milwaukee County"
    assert addresses_by_line1["4041 N RICHARDS ST"].state == "WI"
    assert len(aliases) == 1
    assert aliases[0].alias_name == "DOE, J"
    assert len(offenses) == 1
    assert offenses[0].offense_name == "Test Offense"
    assert len(photos) == 1
    assert photos[0].image_url == "https://sort.doc.state.wi.us/api/image?photoId=999&located=true"
    assert photos[0].captured_at is not None
    assert photos[0].captured_at.isoformat() == "2024-01-02T03:04:00"
    assert registrant.demographics["doc_num"] == "WI-100"
    assert registrant.demographics["supervising_office"]["phone"] == "414-229-0400"


def test_north_dakota_connector_ingests_full_registry_search(monkeypatch) -> None:
    connector = NorthDakotaRegistryConnector()

    async def fake_fetch_search_results(self, client, *, first: str = "", last: str = ""):
        assert first == ""
        assert last == ""
        return _parse_search_results(_make_north_dakota_search_results_html())

    async def fake_fetch_detail_html(self, client, detail_url: str):
        assert detail_url.endswith("/offender/details/123e4567-e89b-12d3-a456-426614174000")
        return _make_north_dakota_detail_html()

    monkeypatch.setattr(NorthDakotaRegistryConnector, "_fetch_search_results", fake_fetch_search_results)
    monkeypatch.setattr(NorthDakotaRegistryConnector, "_fetch_detail_html", fake_fetch_detail_html)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "north-dakota", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "nd:123e4567-e89b-12d3-a456-426614174000"
    assert registrant.full_name == "DOE, JOHN"
    assert registrant.date_of_birth is None
    assert registrant.sex == "MALE"
    assert registrant.risk_level == "HIGH"
    assert registrant.height_cm == 173
    assert registrant.weight_kg == 100
    assert len(addresses) == 2
    addresses_by_line1 = {address.line1: address for address in addresses}
    assert addresses_by_line1["123 MAIN ST"].city == "BISMARCK"
    assert addresses_by_line1["123 MAIN ST"].county == "BURLEIGH"
    assert addresses_by_line1["456 SIDE ST"].address_precision == "employment"
    assert len(aliases) == 2
    assert {row.alias_name for row in aliases} == {"JOHN DOE", "J DOE"}
    assert len(offenses) == 1
    assert offenses[0].offense_name == "LURING MINOR BY COMPUTER"
    assert offenses[0].statute == "12.1-20-05.1"
    assert len(photos) == 1
    assert photos[0].image_url == "https://sexoffender.nd.gov/photos/profile.jpg"
    assert registrant.demographics["birth_year"] == 1990
    assert registrant.demographics["vehicle_count"] == 1


def test_texas_connector_ingests_county_search_and_rapsheet(monkeypatch) -> None:
    connector = TexasRegistryConnector()

    async def fake_fetch_search_page(self, client):
        return _make_texas_county_search_page_html()

    async def fake_fetch_county_results(self, client, *, county_code: str, token: str):
        assert county_code == "001"
        assert token == "tx-token"
        return _make_texas_county_results_html()

    async def fake_fetch_detail_xml(self, client, sid: str):
        assert sid == "17361344"
        return _make_texas_rapsheet_xml()

    monkeypatch.setattr(TexasRegistryConnector, "_fetch_search_page", fake_fetch_search_page)
    monkeypatch.setattr(TexasRegistryConnector, "_fetch_county_results", fake_fetch_county_results)
    monkeypatch.setattr(TexasRegistryConnector, "_fetch_detail_xml", fake_fetch_detail_xml)

    engine = _sqlite_engine()
    SQLModel.metadata.create_all(
        engine,
        tables=[
            Registrant.__table__,
            Address.__table__,
            Alias.__table__,
            IngestionRun.__table__,
            SourceRecord.__table__,
            Offense.__table__,
            Photo.__table__,
            IngestionCheckpoint.__table__,
        ],
    )

    monkeypatch.setattr("registry.services.get_connector", lambda source: connector)

    with Session(engine) as session:
        async def run_ingest():
            return await ingest_source(session, "texas", dry_run=False, batch_size=1)

        run = anyio.run(run_ingest)
        checkpoint = session.exec(select(IngestionCheckpoint)).one()
        registrant = session.exec(select(Registrant)).one()
        addresses = session.exec(select(Address).order_by(Address.id)).all()
        aliases = session.exec(select(Alias).order_by(Alias.id)).all()
        offenses = session.exec(select(Offense).order_by(Offense.id)).all()
        photos = session.exec(select(Photo).order_by(Photo.id)).all()

    assert run.status == "completed"
    assert checkpoint.last_external_id == "tx:17361344"
    assert registrant.full_name == "SANDERS,ALTON JAKE"
    assert registrant.date_of_birth.isoformat() == "2004-02-09"
    assert registrant.sex == "Male"
    assert registrant.race == "White"
    assert registrant.ethnicity == "Non-Hispanic"
    assert registrant.height_cm == 175
    assert registrant.weight_kg == 68
    assert registrant.eye_color == "BROWN"
    assert registrant.hair_color == "BROWN"
    assert registrant.risk_level == "MODERATE"
    assert len(addresses) == 1
    assert addresses[0].line1 == "160 COUNTY ROAD 1059"
    assert addresses[0].city == "ELKHART"
    assert addresses[0].state == "TX"
    assert addresses[0].postal_code == "75839"
    assert addresses[0].county == "ANDERSON"
    assert len(aliases) == 4
    assert {row.alias_name for row in aliases} == {"AJ,XX", "SANDERS,ALTON JAMES", "JOYCE,ALTON JAMES", "A,J"}
    assert len(offenses) == 1
    assert offenses[0].offense_name == "AGGRAVATED SEXUAL ASSAULT OF A CHILD"
    assert offenses[0].conviction_date.isoformat() == "2023-02-09"
    assert offenses[0].statute == "TEXAS PENAL CODE 22.021(a)(1)(B)"
    assert offenses[0].victim_age == "12"
    assert offenses[0].victim_gender == "Female"
    assert "PROBATION/COMMUNITY SUPERVISION" in offenses[0].disposition
    assert len(photos) == 2
    assert {
        photo.image_url for photo in photos
    } == {
        "https://sor.dps.texas.gov/PublicSite/Search/Rapsheet/CurrentPhoto?Sid=17361344",
        "https://sor.dps.texas.gov/PublicSite/Search/Rapsheet/Photo?photoId=10689397",
    }
    assert registrant.demographics["dps_number"] == "17361344"
    assert len(registrant.demographics["registration_events"]) == 2
    assert registrant.demographics["registration_events"][0]["event_type"] == "Change of Status"
