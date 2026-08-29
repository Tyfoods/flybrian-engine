"""Reviewed collection authorities for the C148-C156 standing estate."""

from __future__ import annotations

import hashlib
import json
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .historical_envelopes import (
    STATIC_PYTHON_EXTRACTOR_ID,
    STATIC_PYTHON_EXTRACTOR_VERSION,
    HistoricalSourceAuthority,
)
from .historical_normalization import (
    HistoricalArtifactReference,
    HistoricalClaim,
    HistoricalNormalizationBundle,
    HistoricalNormalizationError,
    HistoricalRunOccurrence,
    NormalizedExperimentDefinition,
    canonical_json_bytes,
    canonical_sha256,
)

_RESULT_CONTAINERS = (
    "results",
    "all_results",
    "runs",
    "multi_seed",
    "per_seed",
    "sweep_results",
    "seed_results",
)

_OPERATIONAL_RESULT_FIELDS = frozenset({"elapsed_s", "runtime_s", "time_s"})
_OUTCOME_FIELDS = frozenset(
    {
        "_score",
        "azevedo_drop",
        "azevedo_drop_cm",
        "azevedo_drop_pct",
        "coord_metrics",
        "coordination",
        "ctrl78_dev",
        "diagnostic",
        "dof_analysis",
        "elev_500ms",
        "elev_post_silence",
        "elev_pre_silence",
        "elev_ratio",
        "elev_trajectory",
        "elevation",
        "error",
        "final_elev",
        "gate_pass",
        "height_cv",
        "mean_elev",
        "mean_height_steady",
        "mean_tarsi",
        "metrics",
        "mn_rates",
        "mn_spikes",
        "n_neurons",
        "n_novel_premn",
        "n_total_spikes",
        "overshoot_pct",
        "pass",
        "per_act_dev",
        "per_dof_corr",
        "post_elev",
        "pre_elev",
        "premn_spikes",
        "result",
        "results",
        "rise_time_ms",
        "score",
        "seg_contact",
        "slow_rate",
        "standing_metrics",
        "tarsi",
        "walk_metrics",
        "walking",
    }
)
_CLAIM_FIELDS = frozenset({"desc", "exp", "exp_idx", "label", "name", "stage", "test"})
_SEED_FIELDS = frozenset({"random_seed", "seed"})


class _DecimalToken(str):
    """Exact decimal token distinguished from a JSON string value."""


@dataclass(frozen=True)
class StandingCollectionAuthority:
    """Exact writer/result binding for one retained historical collection."""

    collection_id: str
    source_path: str
    source_sha256: str
    result_path: str
    result_sha256: str
    result_byte_length: int
    row_count: int
    duration_ms: int
    archive_member: str | None = None
    container_sha256: str | None = None
    container_byte_length: int | None = None

    @property
    def evidence_locator(self) -> str:
        if self.archive_member is None:
            return self.result_path
        return f"{self.result_path}!{self.archive_member}"

    def to_dict(self) -> dict[str, object]:
        return {
            "collection_id": self.collection_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "result_byte_length": self.result_byte_length,
            "row_count": self.row_count,
            "duration_ms": self.duration_ms,
            "archive_member": self.archive_member,
            "container_sha256": self.container_sha256,
            "container_byte_length": self.container_byte_length,
        }


def _collection(
    collection_id: str,
    source_path: str,
    source_sha256: str,
    result_path: str,
    result_sha256: str,
    result_byte_length: int,
    row_count: int,
    *,
    duration_ms: int = 3_000,
    archive_member: str | None = None,
    container_sha256: str | None = None,
    container_byte_length: int | None = None,
) -> StandingCollectionAuthority:
    return StandingCollectionAuthority(
        collection_id=collection_id,
        source_path=source_path,
        source_sha256=source_sha256,
        result_path=result_path,
        result_sha256=result_sha256,
        result_byte_length=result_byte_length,
        row_count=row_count,
        duration_ms=duration_ms,
        archive_member=archive_member,
        container_sha256=container_sha256,
        container_byte_length=container_byte_length,
    )


STANDING_COLLECTIONS = (
    _collection(
        "c148-phase0",
        "scripts/standing/c148_phase0_standing_test.py",
        "321fe10609d7926da4a3ac8bd0b94a0a249d0b90240d25aedc5572c43d4ca784",
        "output/c148_phase0/phase0_results.json",
        "dbc9abdab7c7b1bedb3f7bd266efc134ada65798de09f35de869d8697ab5337b",
        24_124,
        25,
    ),
    _collection(
        "c148-phase0b",
        "scripts/standing/c148_phase0b_stance_authority.py",
        "101af7f9c86e8585208002878b904b42a07ba2c13fb73737ee697eac2f8ee3b6",
        "output/c148_phase0b/phase0b_results.json",
        "53d0ce7332c90fd300507c4ed2863f029b8c8aa91722289f802bc62ae0dc6cc1",
        70_462,
        70,
    ),
    _collection(
        "c148-phase1",
        "scripts/standing/c148_phase1_quiet_standing.py",
        "df248fe2f7bc429b1074c78e1cc9e10715ab7f45a45ce55c6c27e972c41975ac",
        "output/c148_phase1/phase1_results.json",
        "f50eded4f6115c94356739f1e3c9d0ca3a7099bb4f6708115babe1a98d77bd43",
        65_435,
        60,
    ),
    _collection(
        "c148-phase1c",
        "scripts/standing/c148_phase1c_perstep_standing.py",
        "325f321ab7443d2a6811ae44ac6d6722c86e468d2789bb63d082f5c7fc7e940b",
        "output/c148_phase1c/phase1c_results.json",
        "63b85f6ff4494ebb2440d66a3eb2a4e0b24dec7e31221b19b0504c320abee570",
        70_500,
        65,
    ),
    _collection(
        "c148-phase1d",
        "scripts/standing/c148_phase1d_continuous_perstep.py",
        "68574b1fbaa12da350e4595f2019ae7379ce412a44389e8a99b0bc242e5588e1",
        "output/c148_phase1d/phase1d_results.json",
        "659713144f11aab6f7351b23751b8fa9147c13489ac6cfe014554dd96e71c1e7",
        55_948,
        55,
    ),
    _collection(
        "c148-phase1e",
        "scripts/standing/c148_phase1e_target_search.py",
        "7033792768ce741032d115e2f23c132d19b771bff7a6096f8834a6bc6990c241",
        "output/c148_phase1e/phase1e_results.json",
        "409d720383a17bef46dfe72cd51bac60382f67340d802f0e71fa325afea65718",
        50_417,
        109,
    ),
    _collection(
        "c148-phase1f",
        "scripts/standing/c148_phase1f_standing_validation.py",
        "b5216ca031c04b445e07bd909b445f076f035573209630ec55d0e96ce5379d3b",
        "output/c148_phase1f/phase1f_results.json",
        "d7e761cc15c2adc682a41d2b4c976a352b8258ba16b9e5e4cf8be4e284934591",
        56_097,
        55,
    ),
    _collection(
        "c148-phase2-validation",
        "scripts/standing/c148_phase2_validation.py",
        "b2344a99136f6786c91d7f14b695e75362dd92f1d7dc5db2b710474f0054d6af",
        "output/c148_phase2_validation/validation_results.json",
        "537d2a3c3b7e4c029f166ed16db7b05027f096f049f4f111aeecb974ccc69dda",
        22_635,
        15,
    ),
    _collection(
        "c148-phase2a",
        "scripts/standing/c148_phase2a_dnp09_walking.py",
        "4a0e2b9861a544f99aa7f7b363f5647299bd5b20123be8f1afee577c9f5c298d",
        "output/c148_phase2a/phase2a_results.json",
        "228cddca3afa7ccd0bf5331ea792633d46a732bd1046b9de34304ed251a9479d",
        83_527,
        57,
    ),
    _collection(
        "c148-phase2a2",
        "scripts/standing/c148_phase2a2_alpha_sweep.py",
        "3f829c2d0626f31baabb3cddf5a7e0ec4f776010f95d57ca50010ba2d91c6a78",
        "output/c148_phase2a2/phase2a2_results.json",
        "0d95e15e939a7673c6d4b29911fce0d2f1673b09a711da359202af7b76cd206e",
        77_861,
        51,
    ),
    _collection(
        "c148-phase2b",
        "scripts/standing/c148_phase2b_dn_comparison.py",
        "a95e10f803dee7417be5ffabfcf121d7260c167413a8d5644914d6ec8885df77",
        "output/c148_phase2b/phase2b_results.json",
        "8124e194cd235bcc63c296fc65eff768f43b354b7dfb67898f8b6570c26b1f77",
        59_064,
        39,
    ),
    _collection(
        "c148-phase4",
        "scripts/standing/c148_phase4_assessment.py",
        "d19dc1a215676c4886c0c84502ee0a1bf56a5a4f3fcba7cc7372b7dd5ca2bd71",
        "output/c148_phase4/phase4_results.json",
        "365d65c28e85a1f3a0aea0de5dbffd139e7fdb4bb0f2881d9e6e957f99295c62",
        15_367,
        11,
    ),
    _collection(
        "c149-phase0",
        "scripts/standing/c149_phase0_interleg_survey.py",
        "dd3b2e23f3bd37c5af6d61b64b737ca4b45258e4dd50333eb4ad30023a24ed06",
        "output/c149_phase0/phase0_results.json",
        "887f155ef044cf80efa5f6877c883c6737d09e3f5aabcc87d56156e045ac462b",
        44_831,
        24,
    ),
    _collection(
        "c149-phase1",
        "scripts/standing/c149_phase1_coordination.py",
        "fa6a037802f167dc6a64d5d74034202c6dab30d9e7d092ad866ec7db4c7ec63c",
        "output/c149_phase1/phase1_results.json",
        "cc6a20047838141a2f3b1de824caf28875ecf6ffd92b83b23888a0dd122d2032",
        101_177,
        48,
    ),
    _collection(
        "c149-phase2",
        "scripts/standing/c149_phase2_stance_asymmetry.py",
        "f7a8b1b07b7139fbdb91ff9bafd95187a34defc4b965889df40fbadeec6c87ca",
        "output/c149_phase2/phase2_results.json",
        "96638bf12ecf45824417e66690bf797ce03987820618528360a37d024684c22d",
        152_047,
        72,
    ),
    _collection(
        "c149-phase3",
        "scripts/tools/c149_phase3_validation_video.py",
        "20754c229c9b52758e874fc28c158121602e3935ea3038e80a22105810e6351b",
        "output/c149_phase3/phase3_results.json",
        "4d681c99a3ace19e099f3ebb346585eda71c1ec1f2b8ec52f1576df22d4b2a06",
        40_760,
        20,
    ),
    _collection(
        "c150-phase0",
        "scripts/standing/c150_phase0_hh_characterization.py",
        "18ea7409284026b8a561aacdad6bef0ffa48a0c5bce75d7a1d5fbe8fedda4da5",
        "output/c150_phase0.tar.gz",
        "ad426b4a852e1e0b349c90e90842a744fd1b0ef7a0088defa94b273dbba0a44a",
        1_628_969,
        21,
        duration_ms=500,
        archive_member="c150_phase0/phase0_results.json",
        container_sha256="2591c7f9e5862c440a1c2181b85deb508d8385e12dfe8b942eb6512e1ffb3cee",
        container_byte_length=402_541,
    ),
    _collection(
        "c150-phase1",
        "scripts/standing/c150_phase1_tonic_standing.py",
        "5e59948686bfad9b4505ab377d23165b1c94d96e29122abdea6d285c10d5734e",
        "output/c150_phase1/phase1_results.json",
        "a929d34ce67b2f6bb5ad7480e0a87b4959df9e12da20e40d7fda736bb79cd952",
        45_249,
        40,
    ),
    _collection(
        "c150-phase1b",
        "scripts/standing/c150_phase1b_mn_motor_mapping.py",
        "d790f6267b59dc80b5da8ce8fe4ae08652b14f601cb18157e1de23ed30ee8146",
        "output/c150_phase1b/phase1b_results.json",
        "431f79d9c5d7454323dc927bbeb400a6db0acce92d659d65ae6c9b32a1e690ae",
        48_870,
        40,
    ),
    _collection(
        "c150-phase2",
        "scripts/standing/c150_phase2_authority_transfer.py",
        "55e963332fd19cb54173dd91411273cb76a620cab5665268da03e66cde8c4e3b",
        "output/c150_phase2/phase2_results.json",
        "3f7d0fd6340e6fc6b6f98990201d17c1a778808da16cdd60c28edaf1ed1ce599",
        69_060,
        60,
    ),
    _collection(
        "c150-phase2b",
        "scripts/tools/c150_phase2b_force_diagnostic.py",
        "705404b544003ae06d57be02e45efca7190cff3d165bd7046450bbc2ef0e1c9e",
        "output/c150_phase2b/phase2b_results.json",
        "830aaf66666c16f94918ab3602436760ef485633f53fed8aaadc89e6151263a6",
        140_733,
        10,
    ),
    _collection(
        "c150-phase2c",
        "scripts/standing/c150_phase2c_aligned_standing.py",
        "cf6c4978ba905294ade4da7aef2bdd53c18b4461de87f78421ae61b99a86d5e8",
        "output/c150_phase2c/phase2c_results.json",
        "736f38abb9e3fd360984ebb6f68616bba3bf403d4366aca3b7b6b5a995af2fd5",
        111_787,
        96,
    ),
    _collection(
        "c150-phase3",
        "scripts/standing/c150_phase3_hyperpolarization.py",
        "61078cce6afd0c7380cf88edfb3aa3ef79b0491d14df61e530b78da48619306a",
        "output/c150_phase3/phase3_results.json",
        "7b085773abfd7add5fc2a88a6a9dc46e3cb811821fa325014a6f00eb4ec7906d",
        41_058,
        13,
    ),
    _collection(
        "c150-phase4",
        "scripts/standing/c150_phase4_validation.py",
        "ecbba67858ab18c1d42802228783c7307fe6834ddaecba14f5505f8125c8d884",
        "output/c150_phase4/phase4_results.json",
        "fd384c3f782b91f298db7155f2f2d06f302d4db0985185ca073c145c96d6e7c0",
        44_199,
        100,
    ),
    _collection(
        "c151-phase0",
        "scripts/standing/c151_phase0_dnp09_standing.py",
        "9d521a0f2cf9a97e3f9317bb440c5eda1eaa6ce2c37b0dcfcaa4ca429d8e36e5",
        "output/c151_phase0.tar.gz",
        "9ed424a2c8a2fda2e952511372c53e50d38e2ef3589dc5b1cf2fa9e8a4a230d4",
        8_588,
        11,
        archive_member="c151_phase0/phase0_results.json",
        container_sha256="ab1747950ced0a4f1a3963f056d43cebad6491e1032e330cf422a76608ee2ca5",
        container_byte_length=302_064,
    ),
    _collection(
        "c151-phase1",
        "scripts/standing/c151_phase1_height_gated.py",
        "04d959eb41ceb91869c595222ac052686ffd2e2b01875531a408b14106f56db5",
        "output/c151_phase1.tar.gz",
        "f31b83b474f8ebbe989ebd5fe7def42fd7044eedfe3efbd40c0b0dc93d385623",
        31_610,
        36,
        archive_member="c151_phase1/phase1_results.json",
        container_sha256="6bbc4bab1e1bd6aaf105a276aefc9808686fc8221614c6ad034e2d15b46b7717",
        container_byte_length=948_110,
    ),
    _collection(
        "c151-phase1b",
        "scripts/standing/c151_phase1b_motor_scale.py",
        "51c1830521af7bc107ad038864b75da4f0d7ed0e429d29858b7a2f1e1b707ecd",
        "output/c151_phase1b.tar.gz",
        "32c12b39c8904b7a9f8a1b758bad1a01ffa89bb847a2d4bb488360ba85f36dc8",
        20_432,
        24,
        archive_member="c151_phase1b/phase1b_results.json",
        container_sha256="be186d64cc9f069b7428ddf3693d1cb7fdcba5ebbae287c7eef24f8880e4fe45",
        container_byte_length=624_475,
    ),
    _collection(
        "c152-phase0",
        "scripts/standing/c152_phase0_scaffold_free.py",
        "a94f920483fccabb1946ffb03c951fddf5249d4c0e3791010eab3f2bd63116ea",
        "output/c152_phase0.tar.gz",
        "16b41a1f3a2bb1770e42bec630516c10ccd733de689fbff457063576050af389",
        3_808,
        7,
        archive_member="c152_phase0/phase0_results.json",
        container_sha256="87f0ad74ec4aa71d45cded00d0de344c6417589266d1da6435a5c9140f1bbaf6",
        container_byte_length=186_786,
    ),
    _collection(
        "c152-phase1",
        "scripts/tools/c152_phase1_feedback_trace.py",
        "a929a17dc88a29865cac424f9b67d3eeb2563a2075c972e26490e352ecab0226",
        "output/c152_phase1.tar.gz",
        "1742d47ab94fd3288baf24235f3b039b78b9db93763b2d3f05a487a7ef2b9280",
        15_103,
        36,
        archive_member="c152_phase1/phase1_results.json",
        container_sha256="36b30f3a5358d44097df7d96d485b1fddd195f7b6df571fb161353d3ac1b132e",
        container_byte_length=566_984,
    ),
    _collection(
        "c152-phase2",
        "scripts/tools/c152_phase2_mapping_calibration.py",
        "f70e765660102d31a2b0f01955d02d140e143e6a363a86c3af2a99a1e7a4d5b3",
        "output/c152_phase2.tar.gz",
        "833c80269fe8f146293f333b4981ee4d443b3d31ca00ec3b16fa126019db40bf",
        15_118,
        33,
        archive_member="c152_phase2/phase2_results.json",
        container_sha256="77bbe55af709854f4ef1067eb1db64d951672cdb5c386fa5fbf278978aabeb4b",
        container_byte_length=607_457,
    ),
    _collection(
        "c153-phase1",
        "scripts/standing/c153_phase1_premotor_integration.py",
        "d0f567d62c9d86864596e9faed69ec826f4c0070110d55a256d02c560a182d6a",
        "output/c153_phase1/phase1_results.json",
        "a879fbd5eb5ebdc7f07bef4a2b0a5ef5f3d29e756e140d83817540cefd466f97",
        11_135,
        24,
    ),
    _collection(
        "c153-phase2",
        "scripts/standing/c153_phase2_asymmetry_refinement.py",
        "ad160dd2064b1068b261948d9e0ea3fdcefb1c13e8fb99cf0553c154a50a2ce1",
        "output/c153_phase2/phase2_results.json",
        "b26d3570533c10dfedb785b1a0adcb0ca5e525b454619119097cd40204ebbac4",
        10_328,
        19,
    ),
    _collection(
        "c154-phase1",
        "scripts/standing/c154_phase1_unnormalized_sweep.py",
        "767bc6eb6a29a002affb1b7a28517c396bf521d42ab44c9e453dfe3d0510d53d",
        "output/c154_phase1/phase1_results.json",
        "27d4655c10a70353a78ce6658be5ca8a35c38356c87d837bc454820f57349a52",
        33_368,
        50,
    ),
    _collection(
        "c154-phase1b",
        "scripts/standing/c154_phase1b_corrected_sweep.py",
        "e33e6cf0504417e3a258c86f6fd30ab73330cddcf3d47b21341727b1ab98e70a",
        "output/c154_phase1b/phase1b_results.json",
        "4857c812417952d856653bf0cf6d3078a2f37e80d9e9b00695812dff453acd34",
        30_710,
        47,
    ),
    _collection(
        "c154-phase2",
        "scripts/standing/c154_phase2_dual_channel.py",
        "4c03121646506e3b433e4c0f321dd5cfbc02e9e9363bc06774f13d0b9d6b24c6",
        "output/c154_phase2/phase2_results.json",
        "f19d5f80cc0c1003f68eb1483054e4033081093370f1b3fe1da56c598531c824",
        5_378,
        15,
    ),
    _collection(
        "c154-phase3",
        "scripts/standing/c154_phase3_torque_actuation.py",
        "fcfc451305c2fdadbcfedcb81bc761cfdc7f7ad4b5616d13c84604310803d797",
        "output/c154_phase3/phase3_results.json",
        "7cef8691a4db54a55b91e9acc9d3b9fec64a634763ee260550ab4eba3009e820",
        12_022,
        37,
    ),
    _collection(
        "c155-phase1",
        "scripts/standing/c155_phase1_position_velocity_servo.py",
        "72461e7b3d4eea1a00fee75c363065e7488a8fc2915672ec0e212b7bdc4a56a8",
        "output/c155_phase1/phase1_results.json",
        "be83af463551064ddd40c2fffe865cb306e4619d63b673e668458a663ea1c642",
        30_205,
        75,
    ),
    _collection(
        "c155-phase1b",
        "scripts/standing/c155_phase1b_direct_mn_servo.py",
        "48d9a8ea7c3ece00ddcabe48bdd4de062c8c4fd8250595c32064ba368cc8118e",
        "output/c155_phase1b/phase1b_results.json",
        "9581e189cad3dcdb159b5a9420a6065b144a683b3e5ad2ac4146389e07e6ba34",
        46_269,
        72,
    ),
    _collection(
        "c155-phase1c",
        "scripts/standing/c155_phase1c_bidir_velocity_targeted.py",
        "b795a72bf6d97cc012fce0cb471c0e691797f87a38e09d8327a5315961cb7be3",
        "output/c155_phase1c/phase1c_results.json",
        "cb94286b84c3ff6f28eb31040212cdcae5316afdfd3259ad25b540b3c3a72e85",
        23_138,
        59,
    ),
    _collection(
        "c155-phase1d",
        "scripts/standing/c155_phase1d_contact_gated_velocity.py",
        "3d287c5ec8cda6635a59627981f415ffae21c7790e5aaf0a6d5590127aae5fb6",
        "output/c155_phase1d/phase1d_results.json",
        "02f01afc419166fa4471fd08b55ad9d12c8c8abda806f04b239199792ba3ceac",
        17_825,
        45,
    ),
    _collection(
        "c156-phase1",
        "scripts/standing/c156_phase1_muscle_characterization.py",
        "98241d0e962b99d96cefefa25895611b0cdaa425e15df72769edea1c9d50b7e3",
        "output/c156_phase1/phase1_results.json",
        "81bff7ca742e8c59d276e4132ab7e9b9d2f017a21f1e5d7577087a45ee1e5093",
        18_641,
        52,
    ),
    _collection(
        "c156-phase2",
        "scripts/standing/c156_phase2_neural_muscle_standing.py",
        "c03775e9f8139fe950b9c4f216dc00366a80713ca3abd7122da5dd14bc59e597",
        "output/c156_phase2/phase2_results.json",
        "fd2a6cd30d31d6d6b97906cb796846c913055dd0c38475f7a9b0a470614f8743",
        19_577,
        44,
    ),
    _collection(
        "c156-phase2b",
        "scripts/standing/c156_phase2b_reflex_muscle.py",
        "692e37156b89fe3ecc71664a9f515ba81ce8db704818d92a95752eb152fe0dfd",
        "output/c156_phase2b/phase2b_results.json",
        "8bd56329977db0c0509cd17871580127513c4c97bd0ac3d427df41545023d0b1",
        19_327,
        42,
    ),
)


UNRESOLVED_STANDING_RESULT = {
    "evidence_locator": "output/c148_phase3/phase3c_results.json",
    "sha256": "3b59a3f64e961e88b8b5faf6ae39af14f0f7bb448bf75d8d3335f1243f2eb01b",
    "byte_length": 12_558,
    "row_count": 9,
    "reason": "No retained source declares the phase3c_results.json output basename.",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_collection_result_bytes(
    authority: StandingCollectionAuthority,
    *,
    repository_root: Path,
) -> bytes:
    """Read exact result bytes without extracting archived evidence to disk."""
    path = repository_root / authority.result_path
    if authority.archive_member is None:
        return path.read_bytes()
    container = path.read_bytes()
    if (
        _sha256(container) != authority.container_sha256
        or len(container) != authority.container_byte_length
    ):
        raise HistoricalNormalizationError(
            f"{authority.collection_id} archive container differs from reviewed bytes"
        )
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember(authority.archive_member)
        stream = archive.extractfile(member)
        if stream is None or not member.isfile():
            raise HistoricalNormalizationError(
                f"{authority.collection_id} result member is unavailable"
            )
        return stream.read()


def read_collection_rows(
    authority: StandingCollectionAuthority,
    *,
    repository_root: Path,
) -> tuple[dict[str, object], ...]:
    """Validate a retained result collection and return its exact JSON rows."""
    source = (repository_root / authority.source_path).read_bytes()
    if _sha256(source) != authority.source_sha256:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} writer differs from reviewed bytes"
        )
    result = read_collection_result_bytes(authority, repository_root=repository_root)
    if _sha256(result) != authority.result_sha256 or len(result) != authority.result_byte_length:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} result differs from reviewed bytes"
        )
    loaded: object = json.loads(
        result,
        parse_float=_DecimalToken,
        parse_constant=_DecimalToken,
    )
    rows = loaded if isinstance(loaded, list) else _nested_result_rows(loaded)
    if rows is None or len(rows) != authority.row_count:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} must contain {authority.row_count} rows"
        )
    if not all(isinstance(row, dict) and all(isinstance(key, str) for key in row) for row in rows):
        raise HistoricalNormalizationError(f"{authority.collection_id} rows must be JSON objects")
    return tuple(rows)  # type: ignore[arg-type]


def _nested_result_rows(value: object) -> list[object] | None:
    if not isinstance(value, dict):
        return None
    matches = [value[key] for key in _RESULT_CONTAINERS if isinstance(value.get(key), list)]
    return matches[0] if len(matches) == 1 else None


def build_standing_estate_normalization_bundle(
    *,
    repository_root: Path,
    revision: str,
) -> HistoricalNormalizationBundle:
    """Normalize every exact C148-C156 row while preserving repeated occurrences."""
    definitions: dict[str, NormalizedExperimentDefinition] = {}
    claims: list[HistoricalClaim] = []
    occurrences: list[HistoricalRunOccurrence] = []
    artifacts: list[HistoricalArtifactReference] = []
    for authority in STANDING_COLLECTIONS:
        source = _source_authority(authority, repository_root=repository_root, revision=revision)
        for row_index, row in enumerate(
            read_collection_rows(authority, repository_root=repository_root)
        ):
            configuration = _scientific_configuration(authority, row)
            family_id = f"org.flybrian.family.standing.{authority.collection_id}"
            identity = canonical_sha256(
                {
                    "family_id": family_id,
                    "scientific_configuration": configuration,
                    "source": source.to_dict(),
                }
            )
            definition_id = f"org.flybrian.definition.{authority.collection_id}-{identity[:16]}"
            definitions.setdefault(
                definition_id,
                NormalizedExperimentDefinition(
                    definition_id=definition_id,
                    version="1.0",
                    family_id=family_id,
                    scientific_configuration=configuration,
                    source=source,
                ),
            )
            claim_id = f"org.flybrian.claim.{authority.collection_id}-row-{row_index}"
            occurrence_id = f"org.flybrian.occurrence.{authority.collection_id}-row-{row_index}"
            artifact_id = f"org.flybrian.artifact.{authority.collection_id}-row-{row_index}-result"
            claims.append(
                HistoricalClaim(
                    claim_id=claim_id,
                    definition_id=definition_id,
                    name=_claim_name(authority, row, row_index),
                    description=(
                        f"Retained {authority.duration_ms:,} ms row {row_index} from "
                        f"{authority.evidence_locator}."
                    ),
                    tags=tuple(
                        sorted(
                            {
                                authority.collection_id,
                                authority.collection_id.split("-", 1)[0],
                                "standing",
                            }
                        )
                    ),
                )
            )
            occurrences.append(
                HistoricalRunOccurrence(
                    occurrence_id=occurrence_id,
                    definition_id=definition_id,
                    claim_ids=(claim_id,),
                    evidence=_occurrence_evidence(authority, row_index),
                )
            )
            scientific_result = {
                key: value for key, value in row.items() if key not in _OPERATIONAL_RESULT_FIELDS
            }
            scientific_bytes = canonical_json_bytes(scientific_result)
            artifacts.append(
                HistoricalArtifactReference(
                    artifact_id=artifact_id,
                    definition_id=definition_id,
                    kind="scientific_result",
                    logical_path=(
                        f"normalized/standing/{authority.collection_id}/"
                        f"row-{row_index}/scientific_result.json"
                    ),
                    byte_length=len(scientific_bytes),
                    sha256=_sha256(scientific_bytes),
                    disposition="bound",
                    disposition_reason=(
                        f"Canonical projection of {authority.evidence_locator} JSON row "
                        f"/{row_index}; wall-clock fields are excluded."
                    ),
                    comparison="canonical_json",
                )
            )
    return HistoricalNormalizationBundle(
        bundle_id="org.flybrian.normalization.standing-c148-c156",
        version="1.0",
        definitions=tuple(sorted(definitions.values(), key=lambda item: item.definition_id)),
        claims=tuple(sorted(claims, key=lambda item: item.claim_id)),
        occurrences=tuple(sorted(occurrences, key=lambda item: item.occurrence_id)),
        inputs=(),
        artifacts=tuple(sorted(artifacts, key=lambda item: item.artifact_id)),
        recipes=(),
    )


def _source_authority(
    authority: StandingCollectionAuthority,
    *,
    repository_root: Path,
    revision: str,
) -> HistoricalSourceAuthority:
    source_path = repository_root / authority.source_path
    source = source_path.read_bytes()
    if _sha256(source) != authority.source_sha256:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} writer differs from reviewed bytes"
        )
    return HistoricalSourceAuthority(
        repository="flybrian-serve",
        revision=revision,
        logical_path=authority.source_path,
        byte_length=len(source),
        sha256=authority.source_sha256,
        license_id="proprietary-unpublished",
        access="private",
        redistribution="not-allowed",
        extractor_id=STATIC_PYTHON_EXTRACTOR_ID,
        extractor_version=STATIC_PYTHON_EXTRACTOR_VERSION,
    )


def _scientific_configuration(
    authority: StandingCollectionAuthority,
    row: Mapping[str, object],
) -> dict[str, object]:
    parameters = {
        key: value
        for key, value in row.items()
        if key not in _OPERATIONAL_RESULT_FIELDS
        and key not in _OUTCOME_FIELDS
        and key not in _CLAIM_FIELDS
        and key not in _SEED_FIELDS
    }
    options = [
        {
            "option_id": f"recorded.{key}",
            "label": key.replace("_", " ").title(),
            "value_kind": _value_kind(value),
            "unit": None,
            "resolution_rule": "Exact value recorded by the retained writer result row.",
        }
        for key, value in sorted(parameters.items())
    ]
    resolutions = [
        {
            "option_id": f"recorded.{key}",
            "requested_value": value,
            "effective_value": value,
            "source": "retained_result_row",
        }
        for key, value in sorted(parameters.items())
    ]
    return {
        "requested_duration_ms": authority.duration_ms,
        "effective_duration_ms": authority.duration_ms,
        "random_seed": _row_seed(row),
        "recorded_parameters": parameters,
        "option_definitions": options,
        "option_resolutions": resolutions,
        "implementation": {
            "backend": "historical_python_source",
            "neuron_models": "source_bound",
            "controller": "source_bound",
            "body": "source_bound",
        },
    }


def _row_seed(row: Mapping[str, object]) -> int | None:
    value = row.get("seed", row.get("random_seed"))
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalNormalizationError("standing row seed must be an integer or null")
    return value


def _value_kind(value: object) -> str:
    if isinstance(value, _DecimalToken):
        return "decimal"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "json_list"
    if isinstance(value, dict):
        return "json_object"
    if value is None:
        return "null"
    raise HistoricalNormalizationError("standing row contains an unsupported parameter value")


def _claim_name(
    authority: StandingCollectionAuthority,
    row: Mapping[str, object],
    row_index: int,
) -> str:
    descriptors = [
        f"{key}={row[key]}"
        for key in ("stage", "name", "label", "config", "test", "exp", "exp_idx")
        if key in row and row[key] is not None and str(row[key]).strip()
    ]
    suffix = ", ".join(descriptors[:3]) or f"row {row_index}"
    return f"{authority.collection_id} — {suffix}"


def _occurrence_evidence(
    authority: StandingCollectionAuthority,
    row_index: int,
) -> tuple[str, ...]:
    evidence = [
        f"{authority.evidence_locator}#/{row_index}",
        f"result SHA-256 {authority.result_sha256}",
        f"source SHA-256 {authority.source_sha256}",
    ]
    if authority.container_sha256 is not None:
        evidence.append(f"archive SHA-256 {authority.container_sha256}")
    return tuple(evidence)


def audit_standing_estate(*, repository_root: Path, revision: str) -> dict[str, object]:
    """Reconcile every exact C148-C156 writer/result collection."""
    collection_rows = []
    for authority in STANDING_COLLECTIONS:
        rows = read_collection_rows(authority, repository_root=repository_root)
        collection_rows.append({**authority.to_dict(), "validated_row_count": len(rows)})
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "profile_id": "org.flybrian.standing-estate-authority",
        "profile_version": "1.0",
        "source_repository": "flybrian-serve",
        "source_revision": revision,
        "collection_count": len(STANDING_COLLECTIONS),
        "run_row_count": sum(item.row_count for item in STANDING_COLLECTIONS),
        "collections": collection_rows,
        "unresolved_results": [UNRESOLVED_STANDING_RESULT],
    }
    receipt["sha256"] = canonical_sha256(receipt)
    return receipt
