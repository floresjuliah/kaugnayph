from django.db import models


class UserTypes(models.Model):
    usertypeid = models.AutoField(db_column='UserTypeID', primary_key=True)
    type_name = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'UserTypes'


class Roles(models.Model):
    roleid = models.AutoField(db_column='RoleID', primary_key=True)
    rolename = models.CharField(db_column='RoleName', max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'Roles'


class Permissions(models.Model):
    permissionid = models.AutoField(db_column='PermissionID', primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'Permissions'


class RolePermissions(models.Model):
    role = models.ForeignKey(Roles, models.CASCADE, db_column='RoleID')
    permission = models.ForeignKey(Permissions, models.CASCADE, db_column='PermissionID')

    class Meta:
        db_table = 'RolePermissions'
        unique_together = (('role', 'permission'),)


class Positions(models.Model):
    positionid = models.AutoField(db_column='PositionID', primary_key=True)
    name = models.CharField(db_column='Name', max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'Positions'


class Users(models.Model):

    userid = models.AutoField(
        db_column='UserID',
        primary_key=True
    )

    username = models.CharField(
        db_column='Username',
        max_length=50,
        unique=True
    )

    password = models.CharField(
        db_column='Password',
        max_length=255
    )

    firstname = models.CharField(
        db_column='Firstname',
        max_length=100
    )

    lastname = models.CharField(
        db_column='Lastname',
        max_length=100
    )

    contactno = models.CharField(
        db_column='ContactNo',
        max_length=20,
        unique=True
    )


    email = models.CharField(
        db_column='Email',
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    user_type = models.ForeignKey(
        'UserTypes',
        db_column='user_type_id',
        on_delete=models.CASCADE
    )

    role = models.ForeignKey(
        'Roles',
        db_column='role_id',
        null=True,
        on_delete=models.SET_NULL
    )

    position = models.ForeignKey(
        'Positions',
        db_column='position_id',
        null=True,
        on_delete=models.SET_NULL
    )

    is_verified = models.BooleanField(
        db_column='is_verified',
        default=False
    )

    is_active = models.BooleanField(
        db_column='is_active',
        default=True
    )

    is_first_login = models.BooleanField(
        db_column='is_first_login',
        default=True
    )

    is_password_changed = models.BooleanField(
        db_column='is_password_changed',
        default=False
    )

    class Meta:
        db_table = 'Users'


class OTP(models.Model):
    otpid = models.AutoField(db_column='OtpID', primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    code = models.CharField(db_column='Code', max_length=10, blank=True, null=True)
    purpose = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(db_column='Created_at', auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_used = models.BooleanField(default=False)

    attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'OTP'


class Settings(models.Model):
    settingsid = models.AutoField(db_column='SettingsID', primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    notifications_enabled = models.BooleanField(blank=True, null=True)
    dark_mode = models.BooleanField(blank=True, null=True)
    text_size = models.CharField(max_length=10, blank=True, null=True)
    receive_sms = models.BooleanField(db_column='receive_SMS', blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Settings'


class TypeOfID(models.Model):
    toid = models.AutoField(db_column='ToID', primary_key=True)
    name = models.CharField(db_column='Name', max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'TypeOfID'


class ResidentVerification(models.Model):
    rv_id = models.AutoField(db_column='RV_ID', primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    toid = models.ForeignKey(TypeOfID, models.CASCADE, db_column='ToID', blank=True, null=True)
    id_image = models.BinaryField(blank=True, null=True)
    selfie_image = models.BinaryField(blank=True, null=True)
    id_image_path = models.CharField(max_length=255, blank=True, null=True)
    selfie_image_path = models.CharField(max_length=255, blank=True, null=True)
    reviewed_by = models.ForeignKey(
        Users,
        models.CASCADE,
        db_column='reviewed_by',
        related_name='resident_verifications_reviewed',
        blank=True,
        null=True
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        db_table = 'ResidentVerification'


class DocumentTypes(models.Model):
    dtid = models.AutoField(db_column='DTID', primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'DocumentTypes'


class DocumentFields(models.Model):
    dfid = models.AutoField(db_column='DFID', primary_key=True)
    document_type = models.ForeignKey(DocumentTypes, models.CASCADE, db_column='document_type_id', blank=True, null=True)
    field_label = models.CharField(max_length=100, blank=True, null=True)
    field_type = models.CharField(max_length=20, blank=True, null=True)
    is_required = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'DocumentFields'


class DocumentRequests(models.Model):
    drid = models.AutoField(db_column='DRID', primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    document_type = models.ForeignKey(DocumentTypes, models.CASCADE, db_column='document_type_id', blank=True, null=True)
    request_mode = models.CharField(max_length=20, blank=True, null=True)
    purpose = models.TextField(blank=True, null=True)
    generated_file = models.CharField(max_length=255, blank=True, null=True)
    uploaded_file = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    processed_by = models.ForeignKey(
        Users,
        models.CASCADE,
        db_column='processed_by',
        related_name='document_requests_processed',
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'DocumentRequests'


class DocumentRequestFieldValues(models.Model):
    drfvid = models.AutoField(db_column='DRFVID', primary_key=True)

    document_request = models.ForeignKey(
        DocumentRequests,
        models.CASCADE,
        db_column='document_request_id'
    )

    document_field = models.ForeignKey(
        DocumentFields,
        models.CASCADE,
        db_column='document_field_id'
    )

    field_value = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'DocumentRequestFieldValues'


class ComplaintType(models.Model):
    ctid = models.AutoField(db_column='CTID', primary_key=True)
    type = models.CharField(db_column='Type', max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'ComplaintType'


class Complaints(models.Model):
    complaintsid = models.AutoField(db_column='ComplaintsID', primary_key=True)
    complaint_type = models.ForeignKey(ComplaintType, models.CASCADE, db_column='complaint_type_id', blank=True, null=True)
    complainant_user = models.ForeignKey(Users, models.CASCADE, db_column='complainant_user_id', blank=True, null=True)
    complainee = models.CharField(max_length=255, blank=True, null=True)
    title = models.CharField(db_column='Title', max_length=255, blank=True, null=True)
    description = models.TextField(db_column='Description', blank=True, null=True)
    file = models.BinaryField(db_column='File', blank=True, null=True)
    file_path = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    dateadded = models.DateTimeField(db_column='DateAdded', auto_now_add=True)
    datefinish = models.DateTimeField(db_column='DateFinish', blank=True, null=True)
    handled_by = models.ForeignKey(
        Users,
        models.CASCADE,
        db_column='handled_by',
        related_name='complaints_handled',
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'Complaints'


class ComplaintUpdates(models.Model):
    cuid = models.AutoField(db_column='CUID', primary_key=True)
    complaint = models.ForeignKey(Complaints, models.CASCADE, db_column='complaint_id', blank=True, null=True)
    updated_by = models.ForeignKey(Users, models.CASCADE, db_column='updated_by', blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ComplaintUpdates'


class HearingLevel(models.Model):
    hearinglevelid = models.AutoField(db_column='HearingLevelID', primary_key=True)
    level_type = models.CharField(db_column='Level_Type', max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'HearingLevel'


class HearingStatus(models.Model):
    statusid = models.AutoField(db_column='StatusID', primary_key=True)
    statustype = models.CharField(db_column='StatusType', max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'HearingStatus'


class ComplaintHearing(models.Model):
    chid = models.AutoField(db_column='CHID', primary_key=True)
    complaint = models.ForeignKey(Complaints, models.CASCADE, db_column='complaint_id')
    hearing_level = models.ForeignKey(HearingLevel, models.CASCADE, db_column='hearing_level_id')
    hearing_date = models.DateTimeField()
    status = models.ForeignKey(HearingStatus, models.CASCADE, db_column='status_id')
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ComplaintHearing'


class HearingOfficials(models.Model):
    hoid = models.AutoField(db_column='HOID', primary_key=True)
    complaint = models.ForeignKey(Complaints, models.CASCADE, db_column='complaint_id')
    user_officials = models.ForeignKey(Users, models.CASCADE, db_column='user_officials_id')
    role = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'HearingOfficials'


class SMSSubscriptions(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    is_active = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'SMSSubscriptions'


class SMSOutbox(models.Model):
    outboxid = models.AutoField(db_column='OutboxID', primary_key=True)

    recipient_number = models.CharField(max_length=20, blank=True, null=True)
    message = models.TextField(blank=True, null=True)

    sent_by = models.ForeignKey(
        Users,
        models.CASCADE,
        db_column='sent_by',
        blank=True,
        null=True
    )

    sent_at = models.DateTimeField(blank=True, null=True)

    status = models.CharField(max_length=20, blank=True, null=True)

    error_message = models.TextField(blank=True, null=True)
    gateway_response = models.TextField(blank=True, null=True)

    module_id = models.IntegerField(blank=True, null=True)
    related_record_id = models.IntegerField(blank=True, null=True)
    user_id = models.IntegerField(blank=True, null=True)

    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'SMS_Outbox'

class SMSModules(models.Model):
    smsmoduleid = models.AutoField(db_column='SMSModuleID', primary_key=True)
    module_name = models.CharField(max_length=50)

    class Meta:
        db_table = 'SMSModules'


class AnnouncementCategories(models.Model):
    acid = models.AutoField(db_column='ACid', primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'AnnouncementCategories'


class Announcements(models.Model):
    announcement_id = models.AutoField(db_column='Announcement_id', primary_key=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    category = models.ForeignKey(AnnouncementCategories, models.CASCADE, db_column='category_id', blank=True, null=True)
    file = models.BinaryField(db_column='File', blank=True, null=True)
    file_path = models.CharField(max_length=255, blank=True, null=True)
    posted_by = models.ForeignKey(Users, models.CASCADE, db_column='posted_by', blank=True, null=True)
    send_sms = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Announcements'


class AnnouncementFeedback(models.Model):
    afid = models.AutoField(db_column='AFID', primary_key=True)
    announcement = models.ForeignKey(Announcements, models.CASCADE, db_column='announcement_id')
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id')
    rating = models.IntegerField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'AnnouncementFeedback'
        unique_together = (('announcement', 'user'),)


class Inquiry(models.Model):
    cuid = models.AutoField(db_column='CUID', primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    firstname = models.CharField(db_column='Firstname', max_length=250)
    lastname = models.CharField(db_column='Lastname', max_length=250)
    contactno = models.CharField(db_column='ContactNo', max_length=20)
    address = models.CharField(db_column='Address', max_length=100, blank=True, null=True)
    messagesubject = models.CharField(db_column='MessageSubject', max_length=255, blank=True, null=True)
    message = models.TextField(db_column='Message', blank=True, null=True)
    status = models.CharField(db_column='Status', max_length=20, default='New')
    admin_reply = models.TextField(blank=True, null=True)
    replied_at = models.DateTimeField(blank=True, null=True)
    replied_byuser = models.ForeignKey(
        Users,
        models.CASCADE,
        db_column='replied_byUser',
        related_name='inquiries_replied',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Inquiry'


class SLAModules(models.Model):
    moduleid = models.AutoField(db_column='ModuleID', primary_key=True)
    module_name = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'SLAModules'


class SLATracking(models.Model):
    slaid = models.AutoField(db_column='SLAID', primary_key=True)
    module = models.ForeignKey(SLAModules, models.CASCADE, db_column='module_id', blank=True, null=True)
    record_id = models.IntegerField(blank=True, null=True)
    priority_level = models.CharField(max_length=20, blank=True, null=True)
    sla_deadline = models.DateTimeField(blank=True, null=True)
    first_response_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolution_time_minutes = models.IntegerField(blank=True, null=True)
    sla_status = models.CharField(max_length=20, blank=True, null=True)
    response_time_minutes = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'SLATracking'


class AuditLogs(models.Model):
    logid = models.AutoField(db_column='LogID', primary_key=True)
    user = models.ForeignKey(Users, models.CASCADE, db_column='user_id', blank=True, null=True)
    action = models.CharField(max_length=100)
    module_name = models.CharField(max_length=50, blank=True, null=True)
    table_name = models.CharField(max_length=100, blank=True, null=True)
    record_id = models.IntegerField(blank=True, null=True)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    ip_address = models.CharField(max_length=50, blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'AuditLogs'

#STATUS_CHOICES = [
#    ("Pending",  "Pending"),
#    ("Approved", "Approved"),
#    ("Rejected", "Rejected"),
#]

#status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")