from pydantic import BaseModel,ConfigDict
from typing import Optional,List

class KeyBundleUpload(BaseModel):
    identity_key:str
    signing_public:str
    signed_prekey:str
    signed_prekey_signature:str
    prekey_id:int
    one_time_prekeys:List[str]
    kyber_prekey_public: Optional[str] = None
    kyber_prekey_signature: Optional[str] = None
    
class KeyBundleResponse(BaseModel):
    user_id:int
    device_id: Optional[str] = None
    identity_key:str
    identity_version:int = 1
    signing_public:str
    signed_prekey:str
    signed_prekey_signature:str
    prekey_id:int
    bundle_version:int = 1
    one_time_prekey:Optional[str]
    kyber_prekey_public: Optional[str] = None
    kyber_prekey_signature: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
